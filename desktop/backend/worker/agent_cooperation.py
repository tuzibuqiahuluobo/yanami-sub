"""Desktop hand-off for the existing core conversational protocol, not a host."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import sys

from desktop.backend.worker.runtime import initialize_native_paths, runtime_activity


def run(payload: dict) -> dict:
    from finesub.llm.agent.agent_join import waiting_assignments
    from finesub.llm.agent.agent_paths import conversational_assignment_parent
    from finesub.llm.agent.agent_task_control import runtime_for
    from finesub.llm.agent.agent_task_runtime import CONVERSATIONAL_WATCH_SECONDS
    from finesub.llm.prompts import agent_worker_bootstrap

    parent = conversational_assignment_parent().resolve()
    action = payload.get("action")
    if action == "list":
        rows = []
        for path in waiting_assignments(parent)[:100]:
            if path.is_symlink() or path.resolve().parent != parent:
                continue
            try:
                runtime = runtime_for(path)
                index = json.loads(runtime.index_path.read_text(encoding="utf-8"))
                if index["assignment_id"] != path.name:
                    continue
                rows.append({"id": path.name, "path": str(path),
                    "state": runtime.status(assignment_id=path.name)})
            except (OSError, ValueError, KeyError):
                continue
        return {"assignments": rows}
    identifier = payload.get("assignment", "")
    worker = payload.get("worker", "")
    if not re.fullmatch(r"conv-[A-Za-z0-9_-]{1,160}", identifier) or (
        worker and not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", worker)
    ):
        raise ValueError("Invalid assignment or worker id")
    root = parent / identifier
    if root.is_symlink() or root.resolve().parent != parent:
        raise ValueError("Assignment escaped this installation")
    runtime = runtime_for(root)
    index = json.loads(runtime.index_path.read_text(encoding="utf-8"))
    if index["assignment_id"] != identifier:
        raise ValueError("Assignment identity mismatch")
    if action == "status":
        return runtime.rehydrate(assignment_id=identifier, worker_id=worker)
    if action == "join":
        worker = runtime.register_worker(assignment_id=identifier, worker_id=worker,
                                        kind="conversational")["worker_id"]
        # Never pick a different installation's `finesub` from the global PATH.
        status = runtime.rehydrate(assignment_id=identifier, worker_id=worker)
        control = Path(__file__).with_name("agent_control.py").resolve()
        python_literal = sys.executable.replace("'", "''")
        script_literal = str(control).replace("'", "''")
        task_command = (f"& '{python_literal}' -X utf8 '{script_literal}'" if os.name == "nt" else
            f"{shlex.quote(sys.executable)} -X utf8 {shlex.quote(str(control))}")
        protocol = agent_worker_bootstrap(assignment_root=str(root), assignment_id=identifier,
            worker_id=worker, task_command=task_command,
            watch_minutes=int(CONVERSATIONAL_WATCH_SECONDS // 60),
            durable_status=json.dumps(status, ensure_ascii=False, sort_keys=True))
        shell_note = "Windows: the control commands below use PowerShell syntax. Run them in PowerShell.\n\n" if os.name == "nt" else ""
        return {"assignment": identifier, "worker": worker,
            "bootstrap": shell_note + runtime.read_artifact(index["refs"]["bootstrap"]).rstrip() + "\n\n" + protocol.strip()}
    raise ValueError("Unsupported cooperation action")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.readline())
        with runtime_activity():
            initialize_native_paths()
            result = {"ok": True, "data": run(payload)}
        code = 0
    except Exception as error:
        result = {"ok": False, "error": {"message": str(error)}}
        code = 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
