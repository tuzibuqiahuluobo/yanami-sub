from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from collections.abc import Callable


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


def _preflight_packaged_install(*, log: Callable[[str], None] | None = None) -> bool:
    """Repair the active snapshot, or fail without a PyInstaller traceback."""

    if not getattr(sys, "frozen", False):
        return True

    from desktop.backend.updates.recovery import (
        UPDATE_RELAUNCH_ENV,
        full_update_in_progress,
        prepare_app_startup,
    )

    root = _application_root()
    if log is not None:
        log(f"packaged preflight root={root}")
    updater_relaunch = os.environ.pop(UPDATE_RELAUNCH_ENV, "") == "1"
    if not updater_relaunch and full_update_in_progress(root):
        _show_startup_message(
            "正在完成更新，完成后将自动打开 Yanami Sub，请勿重复启动。\n\n"
            "Yanami Sub is finishing an update and will reopen automatically."
        )
        return False

    # Health rollback must precede _activate_packaged_source, not change the
    # worker snapshot after the launcher has imported a different core.
    if prepare_app_startup(root, log=log) is not None:
        return True

    # Development-era/portable layouts predate versioned app snapshots. Keep
    # them bootable while refusing a modern install whose versions are all
    # incomplete.
    if (
        not (root / "app" / "versions").is_dir()
        and (root / "desktop" / "frontend" / "out" / "index.html").is_file()
        and (root / "src" / "finesub" / "pipeline.py").is_file()
        and (root / "pyproject.toml").is_file()
    ):
        return True

    if log is not None:
        log("startup rejected: no complete compatible app snapshot")
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
            (root / "app" / "current.json").read_text(encoding="utf-8-sig")
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


def run() -> int:
    # Acquire ownership before startup repair, pointer changes or core imports.
    from desktop.backend.launcher.instance import acquire_instance

    try:
        instance = acquire_instance()
    except (OSError, RuntimeError) as error:
        _show_startup_message(str(error))
        return 1
    if instance is None:
        return 0
    from desktop.backend.launcher.instance import instance_domain
    from desktop.backend.launcher.session_log import SessionLog

    try:
        session = SessionLog.open(instance_domain())
    except Exception:
        session = SessionLog.disabled()
    session.write("bootstrap starting; ownership acquired")
    try:
        if not _preflight_packaged_install(log=session.write):
            session.finish("startup rejected before app import")
            return 0
        # Frozen GUI imports do not need to write into the immutable snapshot.
        if getattr(sys, "frozen", False):
            sys.dont_write_bytecode = True
        _activate_packaged_source()
        from desktop.backend.launcher.main import main

        return main(instance=instance, session=session, startup_prepared=bool(getattr(sys, "frozen", False)))
    except BaseException as error:
        session.exception("bootstrap", error)
        session.finish("bootstrap failed")
        raise
    finally:
        session.close()
        instance.close()


if __name__ == "__main__":
    raise SystemExit(run())
