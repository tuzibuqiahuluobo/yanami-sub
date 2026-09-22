from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def _application_root() -> Path:
    configured = os.environ.get("FINESUB_APP_ROOT")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else Path(sys.executable).resolve().parent
    )


def _show_startup_message(message: str) -> None:
    """Use a native dialog before pywebview or the frontend can be loaded."""

    if os.name != "nt":
        print(message, file=sys.stderr)
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            "Yanami Sub",
            0x00000000 | 0x00000030,  # MB_OK | MB_ICONWARNING
        )
    except Exception:
        print(message, file=sys.stderr)


def _preflight_packaged_install() -> bool:
    """Repair the active snapshot, or fail without a PyInstaller traceback."""

    if not getattr(sys, "frozen", False):
        return True

    from desktop.backend.updates.recovery import (
        UPDATE_RELAUNCH_ENV,
        full_update_in_progress,
        repair_active_app_version,
    )

    root = _application_root()
    updater_relaunch = os.environ.pop(UPDATE_RELAUNCH_ENV, "") == "1"
    if not updater_relaunch and full_update_in_progress(root):
        _show_startup_message(
            "正在完成更新，完成后将自动打开 Yanami Sub，请勿重复启动。\n\n"
            "Yanami Sub is finishing an update and will reopen automatically."
        )
        return False

    if repair_active_app_version(root) is not None:
        return True

    # Development-era/portable layouts predate versioned app snapshots. Keep
    # them bootable while refusing a modern install whose versions are all
    # incomplete.
    if (
        (root / "desktop" / "frontend" / "out" / "index.html").is_file()
        and (root / "src" / "finesub" / "pipeline.py").is_file()
        and (root / "pyproject.toml").is_file()
    ):
        return True

    _show_startup_message(
        "安装损坏，请重新安装 Yanami Sub。\n\n"
        "The installation is damaged. Please reinstall Yanami Sub."
    )
    return False


def _activate_packaged_source() -> None:
    if not getattr(sys, "frozen", False):
        return
    root = _application_root()
    try:
        current = json.loads(
            (root / "app" / "current.json").read_text(encoding="utf-8")
        ).get("current")
        versions = (root / "app" / "versions").resolve()
        version_root = (
            (versions / current).resolve()
            if isinstance(current, str)
            else None
        )
    except (OSError, ValueError, AttributeError):
        return
    if version_root is None or not version_root.is_relative_to(versions):
        return
    source = version_root / "src"
    if not (
        (version_root / "pyproject.toml").is_file()
        and (source / "finesub" / "pipeline.py").is_file()
    ):
        return
    source_text = str(source)
    if source_text in sys.path:
        sys.path.remove(source_text)
    sys.path.insert(0, source_text)


_STARTUP_ALLOWED = _preflight_packaged_install()
if _STARTUP_ALLOWED:
    _activate_packaged_source()
    from desktop.backend.launcher.main import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main() if _STARTUP_ALLOWED else 0)
