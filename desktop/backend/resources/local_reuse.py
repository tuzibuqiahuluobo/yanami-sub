"""Reuse verified resource archives already present on local disks."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import string
import threading
import time
from urllib.parse import unquote, urlparse

from finesub_bootstrap.asset_resolve import resolve_asset
from finesub_bootstrap.downloader import DownloadPaused


SEARCH_PATHS_ENV = "FINESUB_RESOURCE_SEARCH_PATHS"
DEFAULT_SCAN_TIMEOUT_SECONDS = 45.0
_SKIP_DIRECTORIES = {
    "$recycle.bin",
    "system volume information",
    "recovery",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "appdata",
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
}


@dataclass(frozen=True, slots=True)
class LocalReuseResult:
    path: Path | None = None
    rejected: int = 0
    scan_timed_out: bool = False


class LocalResourceReuse:
    """Index matching archive names once, then verify them against the manifest.

    The file name only narrows the search. Size and SHA-256 are always checked
    before a file enters FineSub's managed cache, so an old or unrelated local
    archive can never replace the pinned resource.
    """

    def __init__(
        self,
        bootstrap,
        *,
        search_roots: Iterable[Path] | None = None,
        scan_timeout: float = DEFAULT_SCAN_TIMEOUT_SECONDS,
        asset_resolver=resolve_asset,
    ) -> None:
        self.bootstrap = bootstrap
        self.search_roots = (
            tuple(Path(path) for path in search_roots)
            if search_roots is not None
            else None
        )
        self.scan_timeout = max(0.0, scan_timeout)
        self.asset_resolver = asset_resolver
        self._condition = threading.Condition()
        self._scanning = False
        self._scan_complete = False
        self._scan_timed_out = False
        self._candidates: dict[str, list[Path]] = {}

    def prepare(
        self,
        resource_id: str,
        *,
        stage: Callable[[str, str], None] | None = None,
        log: Callable[[str], None] | None = None,
        should_pause: Callable[[], bool] | None = None,
    ) -> LocalReuseResult:
        resources = getattr(self.bootstrap, "resources", {})
        spec = resources.get(resource_id) if isinstance(resources, dict) else None
        if spec is None:
            return LocalReuseResult()

        destination = Path(self.bootstrap.cache_path(resource_id))
        names = {
            destination.name.casefold(),
            unquote(Path(urlparse(spec.asset.url).path).name).casefold(),
        }
        names.discard("")
        asset = None
        rejected = 0
        if destination.is_file():
            asset = self.asset_resolver(spec.asset)
            if _matches(destination, asset.size, asset.sha256):
                if log is not None:
                    log(f"已复用 FineSub 下载缓存：{destination}")
                return LocalReuseResult(path=destination)
            rejected = 1
        if stage is not None:
            stage("waiting", "正在搜索本机已有资源")
        candidates, timed_out = self._candidate_files(names, should_pause)
        candidates = [candidate for candidate in candidates if candidate != destination]
        if should_pause is not None and should_pause():
            raise DownloadPaused("Resource installation paused")

        # Resolving a moving asset can contact its metadata API. Do it only
        # after a same-named local file exists; with no candidate, the normal
        # downloader owns all network work and its progress messages.
        if not candidates:
            if log is not None:
                suffix = "（搜索达到时间上限）" if timed_out else ""
                if rejected:
                    log("FineSub 下载缓存与目标版本不符，将从下载源获取。")
                else:
                    log(f"本机未发现同名资源文件{suffix}，将从下载源获取。")
            return LocalReuseResult(rejected=rejected, scan_timed_out=timed_out)

        asset = asset or self.asset_resolver(spec.asset)
        for candidate in candidates:
            if should_pause is not None and should_pause():
                raise DownloadPaused("Resource installation paused")
            if not _matches(candidate, asset.size, asset.sha256):
                rejected += 1
                continue
            reused = _copy_verified(
                candidate,
                destination,
                size=asset.size,
                sha256=asset.sha256,
            )
            if log is not None:
                log(f"已复用本机资源：{candidate}")
            if stage is not None:
                stage("verifying", "已找到匹配版本，跳过网络下载")
            return LocalReuseResult(
                path=reused,
                rejected=rejected,
                scan_timed_out=timed_out,
            )

        if log is not None:
            log(
                f"发现 {rejected} 个同名本地文件，但大小或 SHA-256 与目标版本不符，"
                "将从下载源获取。"
            )
        return LocalReuseResult(rejected=rejected, scan_timed_out=timed_out)

    def _candidate_files(
        self,
        names: set[str],
        should_pause: Callable[[], bool] | None,
    ) -> tuple[list[Path], bool]:
        with self._condition:
            while self._scanning:
                if should_pause is not None and should_pause():
                    raise DownloadPaused("Resource installation paused")
                self._condition.wait(timeout=0.1)
            if not self._scan_complete:
                self._scanning = True
                owner = True
            else:
                owner = False

        if owner:
            try:
                candidates, timed_out = self._scan(should_pause)
            except Exception:
                with self._condition:
                    self._scanning = False
                    self._condition.notify_all()
                raise
            with self._condition:
                self._candidates = candidates
                self._scan_timed_out = timed_out
                self._scan_complete = True
                self._scanning = False
                self._condition.notify_all()

        with self._condition:
            found = [
                candidate
                for name in names
                for candidate in self._candidates.get(name, ())
            ]
            return _deduplicate(found), self._scan_timed_out

    def _scan(
        self,
        should_pause: Callable[[], bool] | None,
    ) -> tuple[dict[str, list[Path]], bool]:
        expected_names = self._expected_names()
        if not expected_names:
            return {}, False
        started = time.monotonic()
        found: dict[str, list[Path]] = {}
        visited: set[str] = set()

        for root in self.search_roots or _default_search_roots():
            root = Path(root)
            if root.is_file():
                _remember_candidate(root, expected_names, found)
                continue
            if not root.is_dir():
                continue
            for current, directories, files in os.walk(
                root,
                topdown=True,
                followlinks=False,
                onerror=lambda _error: None,
            ):
                if should_pause is not None and should_pause():
                    raise DownloadPaused("Resource installation paused")
                if self.scan_timeout and time.monotonic() - started >= self.scan_timeout:
                    return found, True
                normalized = os.path.normcase(os.path.abspath(current))
                if normalized in visited:
                    directories[:] = []
                    continue
                visited.add(normalized)
                directories[:] = [
                    name
                    for name in directories
                    if name.casefold() not in _SKIP_DIRECTORIES
                    and not _is_junction(Path(current) / name)
                ]
                for name in files:
                    folded = name.casefold()
                    if folded in expected_names:
                        found.setdefault(folded, []).append(Path(current) / name)
        return found, False

    def _expected_names(self) -> set[str]:
        resources = getattr(self.bootstrap, "resources", {})
        if not isinstance(resources, dict):
            return set()
        names: set[str] = set()
        for resource_id, spec in resources.items():
            names.add(Path(self.bootstrap.cache_path(resource_id)).name.casefold())
            name = unquote(Path(urlparse(spec.asset.url).path).name).casefold()
            if name:
                names.add(name)
        return names


def _default_search_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    configured = os.environ.get(SEARCH_PATHS_ENV, "")
    roots.extend(Path(value).expanduser() for value in configured.split(os.pathsep) if value)
    home = Path.home()
    roots.extend(home / name for name in ("Downloads", "Desktop", "Documents"))
    roots.extend(_windows_local_drives())
    return tuple(_deduplicate(roots))


def _windows_local_drives() -> tuple[Path, ...]:
    if os.name != "nt":
        return (Path("/"),)
    try:
        import ctypes

        mask = ctypes.windll.kernel32.GetLogicalDrives()
        get_type = ctypes.windll.kernel32.GetDriveTypeW
        return tuple(
            Path(f"{letter}:\\")
            for index, letter in enumerate(string.ascii_uppercase)
            if mask & (1 << index) and get_type(f"{letter}:\\") in {2, 3}
        )
    except Exception:
        return tuple(
            path
            for letter in string.ascii_uppercase
            if (path := Path(f"{letter}:\\")).exists()
        )


def _remember_candidate(
    path: Path,
    expected_names: set[str],
    found: dict[str, list[Path]],
) -> None:
    name = path.name.casefold()
    if name in expected_names:
        found.setdefault(name, []).append(path)


def _is_junction(path: Path) -> bool:
    predicate = getattr(os.path, "isjunction", None)
    return bool(predicate and predicate(path))


def _matches(path: Path, size: int, sha256: str) -> bool:
    try:
        if not path.is_file() or path.stat().st_size != size:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == sha256
    except OSError:
        return False


def _copy_verified(source: Path, destination: Path, *, size: int, sha256: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        if source.resolve() == destination.resolve():
            return destination
    except OSError:
        pass
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        shutil.copy2(source, temporary)
        if not _matches(temporary, size, sha256):
            raise OSError("Local resource changed while it was being copied")
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return destination


def _deduplicate(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized not in seen:
            seen.add(normalized)
            result.append(path)
    return result
