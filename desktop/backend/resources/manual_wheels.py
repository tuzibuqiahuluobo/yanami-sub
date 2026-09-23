"""Use a verified, manually downloaded wheel when a locked download fails."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import tempfile
import time
import tomllib
from typing import Callable, Iterator
from urllib.parse import unquote, urlsplit

import httpx

from finesub_bootstrap.download_routes import (
    forced_region,
    is_degraded,
    record_failure,
    record_success,
)
from finesub_bootstrap.downloader import DownloadPaused
from finesub_bootstrap.environment import (
    RuntimeEnvironment,
    _install_failure_text,
    _is_retryable_from_mirror,
    _is_retryable_install,
)
from finesub_bootstrap.http_client import NetworkRoute, create_client
from finesub_bootstrap.model_fetch import LOCAL_FAILURE_MARKERS


PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
LOCAL_INSTALL_FAILURE_MARKERS = (
    *LOCAL_FAILURE_MARKERS,
    "failed to read directory",
    "url scheme is not allowed",
    "os error 3",
    "系统找不到指定的路径",
)


def _local_failure(error: BaseException) -> bool:
    detail = _install_failure_text(error)
    return any(marker in detail for marker in LOCAL_INSTALL_FAILURE_MARKERS)


def _network_failure(error: BaseException) -> bool:
    """Retry a transport only for network trouble, never local storage trouble."""

    return not _local_failure(error) and _is_retryable_install(error)


def _missing_uv_archive(error: BaseException) -> bool:
    detail = _install_failure_text(error)
    return "archive-v0" in detail and any(
        marker in detail
        for marker in ("os error 3", "no such file or directory", "系统找不到指定的路径")
    )


def _sample_wheel(
    url: str,
    proxy: str | None,
    should_pause: Callable[[], bool] | None,
) -> float | None:
    """Bounded small-range sample; never fetch a whole wheel for a speed test."""

    if should_pause is not None and should_pause():
        raise DownloadPaused("Python environment installation paused")
    started = time.monotonic()
    received = 0
    try:
        with create_client(
            NetworkRoute("AI dependency probe", proxy),
            timeout=httpx.Timeout(connect=3.0, read=2.0, write=2.0, pool=2.0),
        ) as client:
            with client.stream(
                "GET",
                url,
                headers={"Range": "bytes=0-262143", "Accept-Encoding": "identity"},
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    received += len(chunk)
                    if received >= 256 * 1024 or time.monotonic() - started >= 4:
                        break
                    if should_pause is not None and should_pause():
                        raise DownloadPaused("Python environment installation paused")
    except DownloadPaused:
        raise
    except Exception:
        # A probe is advisory. Missing proxy support or a broken endpoint must
        # never prevent uv from attempting the pinned lock normally.
        return None
    if should_pause is not None and should_pause():
        raise DownloadPaused("Python environment installation paused")
    elapsed = max(time.monotonic() - started, 0.001)
    return received / elapsed if received >= 32 * 1024 else None


def _prefer_faster_lock(
    official: Path,
    mirror: Path,
    environment: dict[str, str],
    *,
    log: Callable[[str], None] | None,
    should_pause: Callable[[], bool] | None,
) -> Path | None:
    """Sample the two pinned torch hosts only when Auto has both choices."""

    torch_urls = []
    for lock in (official, mirror):
        torch = next((wheel for wheel in locked_wheels(lock) if wheel.package == "torch"), None)
        if torch is None:
            return None
        torch_urls.append(torch.url)
    if log is not None:
        log("正在测试 AI 大文件的官方源与国内镜像（每路最多读取 256 KB）")
    proxy = next(
        (
            environment[name]
            for name in (
                "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy",
                "HTTP_PROXY", "http_proxy",
            )
            if environment.get(name)
        ),
        None,
    )
    official_speed = _sample_wheel(torch_urls[0], proxy, should_pause)
    mirror_speed = _sample_wheel(torch_urls[1], proxy, should_pause)

    def mirror_ready() -> bool:
        # The mirrored lock uses two hosts: SJTU for PyTorch and TUNA for the
        # smaller packages. A fast SJTU alone must not select a blocked TUNA.
        pypi_wheel = next(
            (wheel for wheel in locked_wheels(mirror) if wheel.package == "click"),
            None,
        )
        return pypi_wheel is None or _sample_wheel(
            pypi_wheel.url, proxy, should_pause
        ) is not None

    if official_speed is None and mirror_speed is None:
        return None
    if official_speed is None:
        return mirror if mirror_ready() else official
    if mirror_speed is None:
        return official
    if mirror_speed >= official_speed * 1.5:
        return mirror if mirror_ready() else official
    if official_speed >= mirror_speed * 1.5:
        return official
    return None


@dataclass(frozen=True)
class LockedWheel:
    filename: str
    url: str
    sha256: str
    package: str


def locked_wheels(lock: Path) -> list[LockedWheel]:
    try:
        packages = tomllib.loads(lock.read_text(encoding="utf-8"))["packages"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return []
    wheels: list[LockedWheel] = []
    for package in packages:
        archives = [package.get("archive"), *package.get("wheels", [])]
        for archive in archives:
            if not isinstance(archive, dict):
                continue
            url = archive.get("url")
            digest = archive.get("hashes", {}).get("sha256")
            if not isinstance(url, str) or not isinstance(digest, str):
                continue
            filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
            if not filename.endswith(".whl") or Path(filename).name != filename:
                continue
            wheels.append(LockedWheel(filename, url, digest, package["name"]))
    return wheels


def failed_wheel(lock: Path, error: Exception) -> LockedWheel | None:
    detail = f"{error} {getattr(error, 'output', '') or ''}".casefold()
    wheels = locked_wheels(lock)
    for wheel in wheels:
        if wheel.filename.casefold() in detail:
            return wheel
    for wheel in wheels:
        package = re.escape(wheel.package.casefold())
        if re.search(rf"(?<![a-z0-9]){package}(?![a-z0-9])", detail) and sum(
            item.package == wheel.package for item in wheels
        ) == 1:
            return wheel
    return None


def _matches_digest(path: Path, expected: str) -> bool:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return False
    return digest.hexdigest().casefold() == expected.casefold()


def install_lock_name(lock: Path) -> str:
    """uv 0.12 requires the optional PEP 751 lock name to contain no dots."""

    return lock.name.replace(".cn.toml", "-cn.toml")


@contextmanager
def local_lock(
    lock: Path,
    cache: Path,
    log: Callable[[str], None] | None,
) -> Iterator[Path]:
    """Replace only verified wheel URLs in a temporary copy of the lock."""

    text = lock.read_text(encoding="utf-8")
    changed = False
    for wheel in locked_wheels(lock):
        local = cache / "downloads" / wheel.filename
        if not local.is_file():
            continue
        if not _matches_digest(local, wheel.sha256):
            if log is not None:
                log(f"已忽略 SHA-256 不匹配的本地依赖：{wheel.filename}")
            continue
        original = f'url = "{wheel.url}"'
        if original not in text:
            continue
        text = text.replace(original, f'path = "{local.resolve().as_posix()}"', 1)
        changed = True
        if log is not None:
            log(f"使用已校验的本地依赖：{wheel.filename}")
    install_name = install_lock_name(lock)
    if not changed and install_name == lock.name:
        yield lock
        return
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yanami-wheel-", dir=cache) as root:
        patched = Path(root) / install_name
        patched.write_text(text, encoding="utf-8")
        yield patched


class DesktopRuntimeEnvironment(RuntimeEnvironment):
    """Keep the core lock and runtime marker intact while reusing local wheels."""

    def _install_dependencies(
        self,
        uv: Path,
        staging_python: Path,
        environment: dict[str, str],
        *,
        log: Callable[[str], None] | None,
        should_pause: Callable[[], bool] | None,
    ) -> None:
        regional = self.regional_lock()
        cn_lock = self.runtime_lock.with_name(
            self.runtime_lock.name.replace(".toml", ".cn.toml")
        )
        # An explicit source choice is respected. Automatic selection can be
        # wrong when a proxy's egress country differs from the user's network.
        preferred = regional or self.runtime_lock
        if (
            forced_region() is None
            and cn_lock.is_file()
            and not is_degraded(self.paths.data_root, "pypi")
            and not any(
                wheel.package == "torch"
                and (self.paths.cache / "downloads" / wheel.filename).is_file()
                for wheel in locked_wheels(self.runtime_lock)
            )
        ):
            sampled = _prefer_faster_lock(
                self.runtime_lock, cn_lock, environment,
                log=log, should_pause=should_pause,
            )
            if sampled is not None:
                preferred = sampled
                if log is not None:
                    log(
                        "短连接测试优先："
                        + ("国内镜像" if sampled == cn_lock else "官方源")
                        + "；这不代表完整下载速度"
                    )
            other = self.runtime_lock if preferred == cn_lock else cn_lock
            locks = [preferred, other]
        else:
            locks = [regional, self.runtime_lock] if regional else [self.runtime_lock]
        for index, lock in enumerate(locks):
            if log is not None:
                log(
                    "AI 依赖下载源："
                    + ("国内镜像" if lock == cn_lock else "官方源")
                    + "（已校验的依赖可复用）"
                )
            try:
                self._run(
                    [
                        str(uv),
                        "pip",
                        "install",
                        "--python",
                        str(staging_python),
                        "--requirement",
                        str(lock),
                    ],
                    environment,
                    log=log,
                    should_pause=should_pause,
                )
            except DownloadPaused:
                raise
            except Exception as error:
                local_error = _local_failure(error)
                retryable = not local_error and (
                    _is_retryable_from_mirror(error)
                    if lock == cn_lock
                    else _network_failure(error)
                )
                if index + 1 == len(locks) or not retryable:
                    raise
                if lock == cn_lock:
                    record_failure(self.paths.data_root, "pypi")
                if log is not None:
                    log(
                        "当前下载源连接失败，改用"
                        + ("官方源" if lock == cn_lock else "国内镜像")
                        + "重试"
                    )
            else:
                if lock == cn_lock:
                    record_success(self.paths.data_root, "pypi")
                return

    def _run(self, command, environment, *, log, should_pause) -> None:
        if (
            len(command) > 2
            and command[1:3] == ["pip", "install"]
            and "--requirement" in command
        ):
            index = command.index("--requirement") + 1
            with local_lock(Path(command[index]), self.paths.cache, log) as lock:
                patched = [*command]
                patched[index] = str(lock)
                network = dict(environment)
                network.setdefault("UV_HTTP_TIMEOUT", "120")
                network.setdefault("UV_HTTP_RETRIES", "5")
                proxied = any(network.get(name) for name in PROXY_VARIABLES)
                if log is not None:
                    log("AI 依赖传输：" + ("代理" if proxied else "直连"))
                run = super()._run

                def install_with_cache_repair(active_environment: dict[str, str]) -> None:
                    try:
                        return run(
                            patched, active_environment, log=log, should_pause=should_pause
                        )
                    except DownloadPaused:
                        raise
                    except Exception as error:
                        if not _missing_uv_archive(error):
                            raise
                        wheel = failed_wheel(Path(command[index]), error)
                        if wheel is None:
                            raise
                        if log is not None:
                            log(f"本地安装缓存缺失，清理 {wheel.package} 缓存后重试一次")
                        run(
                            [command[0], "cache", "clean", wheel.package],
                            active_environment,
                            log=log,
                            should_pause=should_pause,
                        )
                        return run(
                            patched, active_environment, log=log, should_pause=should_pause
                        )

                try:
                    return install_with_cache_repair(network)
                except DownloadPaused:
                    raise
                except Exception as error:
                    if not proxied or not _network_failure(error):
                        raise
                    if log is not None:
                        log("代理连接失败，改为直连重试")
                    direct = {
                        key: value
                        for key, value in network.items()
                        if key not in PROXY_VARIABLES
                    }
                    return install_with_cache_repair(direct)
        return super()._run(
            command, environment, log=log, should_pause=should_pause
        )
