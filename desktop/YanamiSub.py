from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def _activate_packaged_source() -> None:
    if not getattr(sys, "frozen", False):
        return
    configured = os.environ.get("FINESUB_APP_ROOT")
    root = (
        Path(configured).expanduser().resolve()
        if configured
        else Path(sys.executable).resolve().parent
    )
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


_activate_packaged_source()

from desktop.backend.launcher.main import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
