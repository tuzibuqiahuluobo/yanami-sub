from __future__ import annotations

import json
import os
import subprocess

from desktop.backend.worker.runtime import runtime_activity
from finesub_bootstrap.locks import TASK_ACTIVITY_ROOT_VARIABLE


def invoke(context, payload: dict, *, runner=subprocess.run) -> dict:
    return invoke_worker(context, "desktop.backend.worker.agent_cooperation", payload, runner=runner)


def invoke_worker(context, module: str, payload: dict, *, runner=subprocess.run) -> dict:
    environment = {**os.environ, **context.environment}
    with runtime_activity(environment.get(TASK_ACTIVITY_ROOT_VARIABLE, "")):
        result = runner([context.python_executable, "-X", "utf8", "-m", module],
            input=json.dumps(payload, ensure_ascii=False) + "\n", capture_output=True,
            text=True, encoding="utf-8", errors="replace", env=environment,
            cwd=context.working_directory, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    try:
        envelope = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise ValueError("应用运行环境未返回有效结果，请检查资源页 / Check the Python runtime in Resources") from error
    if not envelope.get("ok"):
        raise ValueError((envelope.get("error") or {}).get("message", "Worker operation failed"))
    return envelope["data"]
