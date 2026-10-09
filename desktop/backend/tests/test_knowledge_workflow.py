from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from desktop.backend.worker import knowledge_workflow as workflow
from desktop.backend.worker.knowledge_main import _dispatch
from desktop.backend.common.models import TaskRequest
from finesub.llm.knowledge.node.repo import KnowledgeRepo


def pair(tmp_path, original="こんにちは", translated="你好", encoding="utf-8"):
    left, right = tmp_path / "原文.srt", tmp_path / "译文.srt"
    left.write_text(f"1\n00:00:00,000 --> 00:00:01,000\n{original}\n", encoding=encoding)
    right.write_text(f"1\n00:00:00,000 --> 00:00:01,000\n{translated}\n", encoding=encoding)
    return {"source_srt": str(left), "refined_srt": str(right)}


def setup_root(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    _dispatch({"action": "maintenance", "command": "new", "args": ["common", "作品", "--intro", "作品", "--type", "其他"]})
    return root


def fake_route(monkeypatch):
    @contextmanager
    def route(values):
        yield TaskRequest.model_validate(values), SimpleNamespace(source="agent", targets=["fake-agent"])
    monkeypatch.setattr(workflow, "_route", route)


def test_pair_encoding_and_exact_timeline(tmp_path):
    values = pair(tmp_path, encoding="utf-16")
    result = workflow.inspect_pair(values)
    assert result["source_encoding"] == "utf-16"
    assert result["pairs"][0]["refined"] == "你好"
    Path(values["refined_srt"]).write_text("1\n00:00:00,001 --> 00:00:01,000\n你好\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Timing mismatch"):
        workflow.inspect_pair(values)


def test_explicit_legacy_encoding(tmp_path):
    values = pair(tmp_path, original="世界", encoding="gb18030")
    with pytest.raises(ValueError, match="encoding"):
        workflow.inspect_pair(values)
    assert workflow.inspect_pair({**values, "source_encoding": "gb18030", "refined_encoding": "gb18030"})["count"] == 1


def test_frozen_proposal_applies_once_without_a_second_model_call(tmp_path, monkeypatch):
    root = setup_root(tmp_path, monkeypatch)
    fake_route(monkeypatch)
    calls = []
    class Client:
        def complete(self, *args, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(content='<knowledge_proposals>\n' + json.dumps({"op": "append_lines", "category": "common", "entry": "作品", "section": "档案", "content": "[译名] 初音未来"}, ensure_ascii=False) + '\n</knowledge_proposals>')
    monkeypatch.setattr("finesub.llm.client.RoleClient", Client)
    before = KnowledgeRepo.open(root).rev
    draft = workflow.generate_pair(root, {**pair(tmp_path), "subject": "common/作品", "request": {"input": "unused", "llm_source": "agent", "llm_agent": "LOCAL_DSH"}})
    assert draft["status"] == "generated"
    assert KnowledgeRepo.open(root).rev == before
    result = workflow.apply_draft(root, draft["draft_id"])
    assert result["status"] == "applied", result
    assert KnowledgeRepo.open(root).rev == before + 1
    assert workflow.apply_draft(root, draft["draft_id"])["status"] == "already_applied"
    assert len(calls) == 1
    assert calls[0]["agent_task_extras"]["kb_tools"] == "propose"


def test_stale_draft_and_path_traversal_rejected(tmp_path, monkeypatch):
    root = setup_root(tmp_path, monkeypatch)
    draft = workflow._draft(root, [{"read_rev": 1, "bindings": [], "proposal_text": "", "allow_categories": ["common"]}], {})
    _dispatch({"action": "maintenance", "command": "new", "args": ["common", "另一作品", "--intro", "作品", "--type", "其他"]})
    with pytest.raises(ValueError, match="Knowledge changed"):
        workflow.apply_draft(root, draft["draft_id"])
    with pytest.raises(ValueError, match="Invalid proposal ID"):
        workflow.apply_draft(root, "../outside")


def test_empty_proposal_is_not_reported_as_update(tmp_path, monkeypatch):
    root = setup_root(tmp_path, monkeypatch)
    draft = workflow._draft(root, [], {})
    assert draft["proposal_count"] == 0
    assert workflow.apply_draft(root, draft["draft_id"])["status"] == "no_change"


def test_commit_receipt_recovers_after_desktop_exit(tmp_path, monkeypatch):
    root = setup_root(tmp_path, monkeypatch)
    proposal = json.dumps({"op": "append_lines", "category": "common", "entry": "作品", "section": "档案", "content": "[译名] 初音未来"}, ensure_ascii=False)
    draft = workflow._draft(root, [{"read_rev": 1, "bindings": [], "proposal_text": proposal, "allow_categories": ["common"]}], {})
    original_save = workflow._save
    def crash(path, value):
        if value.get("apply_reports"):
            raise RuntimeError("desktop exit")
        original_save(path, value)
    monkeypatch.setattr(workflow, "_save", crash)
    with pytest.raises(RuntimeError, match="desktop exit"):
        workflow.apply_draft(root, draft["draft_id"])
    assert KnowledgeRepo.open(root).rev == 2
    monkeypatch.setattr(workflow, "_save", original_save)
    recovered = workflow.apply_draft(root, draft["draft_id"])
    assert recovered["status"] == "applied"
    assert recovered["apply_reports"][0]["recovered"] is True
    assert KnowledgeRepo.open(root).rev == 2


def test_refined_inherits_route_difficulty_and_writable_style(tmp_path, monkeypatch):
    root = setup_root(tmp_path, monkeypatch)
    requests, kwargs_seen = [], []
    @contextmanager
    def route(values):
        requests.append(values)
        yield TaskRequest.model_validate(values), SimpleNamespace(source="agent", targets=["dsh"])
    monkeypatch.setattr(workflow, "_route", route)
    monkeypatch.setattr("finesub.llm.client.RoleClient", lambda: object())
    monkeypatch.setattr("finesub.llm.knowledge.style.resolve_style_selection", lambda *args, **kwargs: SimpleNamespace(mode=args[1], names=[args[0]]))
    def update(**kwargs):
        kwargs_seen.append(kwargs)
        return {"chunks": [], "mode": "refined_aligned"}
    monkeypatch.setattr("finesub.llm.knowledge.update.run_knowledge_update", update)
    payload = {"final_srt": str(tmp_path / "final.srt"), "refined_srt": str(tmp_path / "refined.srt"), "task_id": "task", "request": {"input": "video", "llm_source": "agent", "llm_agent": "LOCAL_DSH", "llm_model": ["knowledge=dsh-capable"], "style": "style/风格", "style_mode": "update", "llm_difficulty": "intermediate"}}
    workflow.generate_refined(root, payload)
    assert requests[0]["llm_agent"] == "LOCAL_DSH"
    assert requests[0]["llm_model"] == ["knowledge=dsh-capable"]
    assert kwargs_seen[0]["style_names"] == ["style/风格"]
    assert kwargs_seen[0]["difficulty"] == "intermediate"
    assert kwargs_seen[0]["apply"] is False
    payload["request"]["style_mode"] = "read"
    workflow.generate_refined(root, payload)
    assert kwargs_seen[1]["style_names"] == ()
