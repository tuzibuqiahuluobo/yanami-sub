"""Use a verified, manually downloaded wheel when a locked download fails."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import tempfile
import tomllib
from typing import Callable, Iterator
from urllib.parse import unquote, urlsplit

from finesub_bootstrap.environment import RuntimeEnvironment


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
        text = text.replace(original, f'url = "{local.resolve().as_uri()}"', 1)
        changed = True
        if log is not None:
            log(f"使用已校验的本地依赖：{wheel.filename}")
    if not changed:
        yield lock
        return
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yanami-wheel-", dir=cache) as root:
        patched = Path(root) / lock.name
        patched.write_text(text, encoding="utf-8")
        yield patched


class DesktopRuntimeEnvironment(RuntimeEnvironment):
    """Keep the core lock and runtime marker intact while reusing local wheels."""

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
                return super()._run(
                    patched, network, log=log, should_pause=should_pause
                )
        return super()._run(
            command, environment, log=log, should_pause=should_pause
        )
