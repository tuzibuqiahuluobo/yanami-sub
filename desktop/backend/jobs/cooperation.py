from __future__ import annotations

import json
import os
import subprocess

from desktop.backend.worker.runtime import runtime_activity
from finesub_bootstrap.locks import TASK_ACTIVITY_ROOT_VARIABLE


def invoke(context, payload: dict, *, runner=subprocess.run) -> dict:
    environment = {**os.environ, **context.environment}
    with runtime_activity(environment.get(TASK_ACTIVITY_ROOT_VARIABLE, "")):
        result = runner([context.python_executable, "-m", "desktop.backend.worker.agent_cooperation"],
            input=json.dumps(payload, ensure_ascii=False) + "\n", capture_output=True,
            text=True, encoding="utf-8", errors="replace", env=environment,
            cwd=context.working_directory, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    envelope = json.loads(result.stdout.strip().splitlines()[-1])
    if not envelope.get("ok"):
        raise ValueError((envelope.get("error") or {}).get("message", "Agent cooperation failed"))
    return envelope["data"]
