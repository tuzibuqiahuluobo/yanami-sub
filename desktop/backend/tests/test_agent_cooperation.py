import pytest

from finesub.llm.agent.agent_task_runtime import AgentTaskRuntime, AgentTaskSpec
from desktop.backend.worker.agent_cooperation import run


def test_cooperation_discovers_own_domain_and_registers_without_claiming(tmp_path, monkeypatch):
    from finesub.llm.agent import agent_paths
    parent = tmp_path / "conversational"
    monkeypatch.setattr(agent_paths, "conversational_assignment_parent", lambda: parent)
    root = parent / "conv-test"
    runtime = AgentTaskRuntime.start_assignment(root, assignment_id=root.name, worker_goal="test",
        sealed=False, max_workers=2, tasks=[AgentTaskSpec(task_id="text", session_type="correction",
            input_hash="sha256:test", goal="Answer", claimable_by=("conversational",))])
    assert [row["id"] for row in run({"action": "list"})["assignments"]] == ["conv-test"]
    joined = run({"action": "join", "assignment": "conv-test"})
    assert joined["worker"] == "conv-1" and "bootstrap" in joined
    assert "agent_control.py" in joined["bootstrap"]
    assert "PowerShell" in joined["bootstrap"]
    assert not runtime.task_record(assignment_id="conv-test", task_id="text")["lease_owner"]
    resumed = run({"action": "join", "assignment": "conv-test", "worker": "conv-1"})
    assert resumed["worker"] == "conv-1"
    with pytest.raises(ValueError, match="Invalid assignment"):
        run({"action": "join", "assignment": "../foreign"})


def test_cooperation_does_not_require_an_installed_cli_or_api_key(tmp_path, monkeypatch):
    from desktop.backend.settings.store import SettingsStore
    from desktop.backend.common.models import TaskRequest
    store = SettingsStore(tmp_path)
    monkeypatch.setattr(store, "_configured_agent_tiers", lambda: set())
    monkeypatch.setattr(store, "_read_keys", lambda: {})
    request = TaskRequest(input="a.wav", stage="final-srt", llm_source="manual",
        llm_model=["conversational-agent"], llm_media="text")
    assert store.validate_request(request) is None
    assert store.validate_request(request.model_copy(update={"llm_retrieval": "native"})) is not None
