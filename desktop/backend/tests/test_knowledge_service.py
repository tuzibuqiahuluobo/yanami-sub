from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from desktop.backend.jobs.launch import WorkerLaunchContext
from desktop.backend.knowledge.service import KnowledgeService


def test_knowledge_parent_holds_a_handoff_lease_before_child_imports(tmp_path):
    from finesub_bootstrap.locks import TASK_ACTIVITY_ROOT_VARIABLE, active_run_count
    root = tmp_path / "user-data"
    def run(*_args, **_kwargs):
        assert active_run_count(root) > 0
        return SimpleNamespace(stdout='{"ok":true,"data":{"revision":0}}', stderr="")
    context = WorkerLaunchContext(python_executable="python.exe", working_directory=str(tmp_path),
        environment={TASK_ACTIVITY_ROOT_VARIABLE: str(root)})
    service = KnowledgeService(root / "knowledge", lambda: context, process_runner=run)
    assert service.snapshot()["revision"] == 0
    assert active_run_count(root) == 0


def test_knowledge_service_uses_the_managed_worker_and_owned_root(
    tmp_path: Path,
) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"ok": True, "data": {"revision": 0, "entries": []}}
            )
            + "\n",
            stderr="",
        )

    context = WorkerLaunchContext(
        python_executable="C:/FineSub/runtime/python.exe",
        working_directory="C:/FineSub/app/current",
        environment={"PYTHONPATH": "C:/FineSub/app/current"},
    )
    service = KnowledgeService(
        tmp_path / "user-data" / "knowledge",
        lambda: context,
        process_runner=run,
    )

    result = service.snapshot()

    command, kwargs = calls[0]
    assert result == {"revision": 0, "entries": []}
    assert command[-2:] == ["-m", "desktop.backend.worker.knowledge_main"]
    assert kwargs["cwd"] == "C:/FineSub/app/current"
    assert kwargs["env"]["FINESUB_KNOWLEDGE_ROOT"] == str(service.root)
    assert json.loads(kwargs["input"])["action"] == "snapshot"
