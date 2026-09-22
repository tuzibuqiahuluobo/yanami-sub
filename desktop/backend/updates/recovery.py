"""Pick the installation back up when a full update did not finish.

A full update empties the install root into `.update/backup-<version>/` and
then copies the new tree in. For the seconds that window is open there is no
executable in the install root at all, and nothing used to look at `.update/`
afterwards: a machine that lost power there had a shortcut pointing at a file
that no longer existed, the only copy of the program sitting in `backup-*`, and
the next update attempt deleting that copy before doing anything else.

So the first thing a start-up does now is check whether the last update left
the install root standing, and put it back if not.
"""

from __future__ import annotations

from collections.abc import Callable
import ctypes
import json
import os
from pathlib import Path
import shutil
import time

from packaging.version import InvalidVersion, Version

from finesub_bootstrap.fsops import remove_tree

from desktop.backend.updates.installer import REQUIRED_APP_FILES

UPDATE_DIRECTORY_NAME = ".update"
BACKUP_PREFIX = "backup-"
#: Present in every healthy install root; its absence is what "unbootable"
#: means here. Kept in sync with `updates.service.MAIN_EXECUTABLE_NAME`.
MAIN_EXECUTABLE_NAME = "Yanami Sub.exe"
FULL_UPDATE_MARKER_NAME = "full-update-in-progress.json"
UPDATE_RELAUNCH_ENV = "YANAMI_SUB_UPDATE_RELAUNCH"
_MARKER_HANDOFF_SECONDS = 30.0

LogCallback = Callable[[str], None]


def _marker(root: Path) -> Path:
    return root / UPDATE_DIRECTORY_NAME / FULL_UPDATE_MARKER_NAME


def mark_full_update(
    root: Path,
    *,
    version: str | None = None,
    updater_pid: int = 0,
) -> Path:
    """Atomically mark the install tree as owned by the full updater."""

    marker = _marker(root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, object] = {}
    if marker.is_file():
        try:
            parsed = json.loads(marker.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                existing = parsed
        except (OSError, ValueError):
            pass
    payload = {
        "version": version if version is not None else existing.get("version", ""),
        "updaterPid": updater_pid,
        "startedAt": existing.get("startedAt", time.time()),
    }
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, marker)
    return marker


def clear_full_update_marker(root: Path) -> None:
    try:
        _marker(root).unlink(missing_ok=True)
    except OSError:
        pass


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    synchronize = 0x00100000
    wait_timeout = 0x00000102
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return False
    try:
        return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
    finally:
        kernel32.CloseHandle(handle)


def full_update_in_progress(
    root: Path,
    *,
    process_is_running: Callable[[int], bool] | None = None,
    now: float | None = None,
) -> bool:
    """Whether a live updater currently owns the installation directory."""

    marker = _marker(root)
    if not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        pid = int(payload.get("updaterPid", 0))
        started_at = float(payload.get("startedAt", marker.stat().st_mtime))
    except (OSError, TypeError, ValueError, AttributeError):
        clear_full_update_marker(root)
        return False
    if pid > 0:
        running = (process_is_running or _process_is_running)(pid)
    else:
        running = (now if now is not None else time.time()) - started_at < _MARKER_HANDOFF_SECONDS
    if not running:
        clear_full_update_marker(root)
    return running


def _app_version_is_complete(version_directory: Path) -> bool:
    return all(
        (version_directory / relative).is_file() for relative in REQUIRED_APP_FILES
    )


def _version_sort_key(path: Path) -> tuple[int, Version, float]:
    try:
        version = Version(path.name)
        valid = 1
    except InvalidVersion:
        version = Version("0")
        valid = 0
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return valid, version, modified


def repair_active_app_version(root: Path) -> str | None:
    """Use the newest complete app version and repair a stale pointer."""

    app_root = root / "app"
    pointer_path = app_root / "current.json"
    pointer: dict[str, object] = {}
    if pointer_path.is_file():
        try:
            parsed = json.loads(pointer_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                pointer = parsed
        except (OSError, ValueError):
            pass
    versions = app_root / "versions"
    current = pointer.get("current")
    if (
        isinstance(current, str)
        and current not in {"", ".", ".."}
        and not any(separator in current for separator in ("/", "\\", ":"))
        and _app_version_is_complete(versions / current)
    ):
        return current

    candidates = (
        sorted(
            (
                entry
                for entry in versions.iterdir()
                if entry.is_dir()
                and not entry.name.endswith(".staging")
                and _app_version_is_complete(entry)
            ),
            key=_version_sort_key,
            reverse=True,
        )
        if versions.is_dir()
        else []
    )
    if not candidates:
        return None
    selected = candidates[0].name
    app_root.mkdir(parents=True, exist_ok=True)
    temporary = pointer_path.with_suffix(".repair.tmp")
    temporary.write_text(
        json.dumps(
            {
                "current": selected,
                "previous": None,
                "pendingHealth": False,
                "healthAttempts": 0,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, pointer_path)
    return selected


def backups(root: Path) -> list[Path]:
    """Every interrupted-update backup, newest first."""

    update_root = root / UPDATE_DIRECTORY_NAME
    if not update_root.is_dir():
        return []
    found = [
        entry
        for entry in update_root.iterdir()
        if entry.is_dir() and entry.name.startswith(BACKUP_PREFIX)
    ]
    return sorted(found, key=lambda entry: entry.stat().st_mtime, reverse=True)


def install_is_bootable(root: Path) -> bool:
    if not (root / MAIN_EXECUTABLE_NAME).is_file():
        return False
    if repair_active_app_version(root) is not None:
        return True
    return (
        (root / "desktop" / "frontend" / "out" / "index.html").is_file()
        and (root / "src" / "finesub" / "pipeline.py").is_file()
        and (root / "pyproject.toml").is_file()
    )


def recover_interrupted_update(
    root: Path,
    *,
    log: LogCallback | None = None,
) -> str | None:
    """Restore the previous version if an update left the root unbootable.

    Returns a message for the user when something was actually done, so the
    app can say what happened rather than silently appearing to downgrade.

    Restoring is automatic because the alternative is not a choice anybody can
    make: with no executable in the install root, there is no interface left to
    offer them one.
    """

    if install_is_bootable(root):
        return None
    available = backups(root)
    if not available:
        return None
    backup = available[0]
    restored: list[str] = []
    for entry in list(backup.iterdir()):
        destination = root / entry.name
        if destination.exists():
            # The new tree already put something here; the backup copy is the
            # stale one. Leave what is in place and drop ours.
            continue
        try:
            shutil.move(str(entry), str(destination))
            restored.append(entry.name)
        except OSError:
            if log is not None:
                log(f"无法恢复 {entry.name}，请手工从 {backup} 取回")
    if not restored:
        return None
    message = (
        f"上次更新未完成，已恢复到更新前的版本（{backup.name}）。"
        "可以重新尝试更新。"
    )
    if log is not None:
        log(message)
    return message


def take_update_error_reports(root: Path) -> list[str]:
    """Read and archive whatever the updater left behind, so it is seen once.

    The updater is a windowed build with no console and no reader: its only way
    to report anything is `<request>.error.txt`, and until now nothing in the
    product ever opened one. A user whose update failed saw the app start on
    the old version with no explanation, indefinitely.
    """

    update_root = root / UPDATE_DIRECTORY_NAME
    if not update_root.is_dir():
        return []
    reports: list[str] = []
    for report in sorted(update_root.glob("*.error.txt")):
        try:
            reports.append(report.read_text(encoding="utf-8", errors="replace"))
            report.replace(report.with_suffix(".txt.seen"))
        except OSError:
            continue
    return reports


def discard_backups(root: Path, *, keep: Path | None = None) -> None:
    """Delete update backups -- only ever called once the root is bootable.

    The old code cleared `source-`/`backup-`/`runner-` at the *start* of the
    next attempt, which is exactly when the previous backup may still be the
    only copy of a working installation.
    """

    if not install_is_bootable(root):
        return
    for backup in backups(root):
        if keep is not None and backup == keep:
            continue
        remove_tree(backup)
