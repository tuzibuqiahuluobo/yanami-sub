from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from desktop.backend.jobs.launch import WorkerLaunchContext
from desktop.backend.knowledge.service import KnowledgeService


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
