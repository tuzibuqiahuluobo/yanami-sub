"""Worker-only initialization normally performed by the core CLI entry point."""
from __future__ import annotations

import sys
import os
from contextlib import nullcontext
from pathlib import Path


def initialize_native_paths() -> None:
    try:
        from finesub.speech.runtime.native_paths import use_utf8_crt_locale
    except ModuleNotFoundError as error:
        if error.name != "finesub.speech.runtime.native_paths":
            raise
        return  # The published 0.5.1 core has no native-path initializer.
    problem = use_utf8_crt_locale()
    if problem:
        print(f"Warning: {problem}", file=sys.stderr)


def runtime_activity(root=None):
    from finesub_bootstrap.locks import TASK_ACTIVITY_ROOT_VARIABLE, holding_activity

    if root is None:
        root = os.environ.get(TASK_ACTIVITY_ROOT_VARIABLE, "")
    return holding_activity(Path(root)) if root else nullcontext()


def record_runtime_success() -> None:
    root = os.environ.get("YANAMI_RUNTIME_ROOT", "")
    version = os.environ.get("YANAMI_RUNTIME_VERSION", "")
    if not root or not version:
        return
    try:
        from finesub_bootstrap.runtime_health import record_success
        record_success(Path(root), version)
    except Exception as error:
        print(f"Warning: runtime success marker was not saved: {error}", file=sys.stderr)
