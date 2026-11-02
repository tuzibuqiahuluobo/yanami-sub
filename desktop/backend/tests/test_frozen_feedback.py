from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

from desktop.backend.common.core_compat import unified_llm_contract
from desktop.backend.common.models import TaskRequest
from desktop.backend.worker import knowledge_feedback as feedback
from desktop.backend.worker import knowledge_workflow as workflow
from desktop.backend.worker.knowledge_main import _dispatch
from finesub.llm.knowledge.node.repo import KnowledgeRepo
from finesub.llm.knowledge.update import derive_task_paths


def task_files(tmp_path):
    from finesub.llm import output_protocol

    paths = derive_task_paths(tmp_path / "日本語_中文.srt")
    paths["final_srt"].write_text("1\n00:00:00,000 --> 00:00:01,000\n初音未来\n", encoding="utf-8")
    refined = tmp_path / "精修.srt"
    refined.write_text(paths["final_srt"].read_text(encoding="utf-8"), encoding="utf-8")
    paths["stable_json"].write_text(json.dumps({"segments": [
        {"id": "1", "start": 0, "end": 1, "text": "初音ミク"},
    ]}), encoding="utf-8")
    values = {"kind": "sub", "position": "1", "start": "0.0", "duration": "1.0", "gap": "0.0",
              "corrected": "初音ミク", "translation": "初音未来", "conf": "", "char_count": "4", "note": "", "spk": ""}
    columns = getattr(output_protocol, "_ANNOTATED_ROW_COLUMNS", output_protocol._ROW_COLUMNS)
    paths["annotated_csv"].write_text(getattr(output_protocol, "ANNOTATED_CSV_HEADER", "# fixture") + "\n" +
        "|".join(values[column] for column in columns) + "\n", encoding="utf-8")
    return paths, refined


def knowledge_root(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    _dispatch({"action": "maintenance", "command": "new", "args": ["common", "作品", "--intro", "作品", "--type", "其他"]})
    return root


def add_style(root, name="字幕风格"):
    from finesub.llm.knowledge.node.proposals import apply_model_proposals

    _dispatch({"action": "maintenance", "command": "new", "args": ["style", name, "--intro", "歌曲翻译风格"]})
    repo = KnowledgeRepo.open(root)
    response = json.dumps({"op": "append_lines", "category": "style", "entry": name,
        "section": "约定", "content": "[歌名] 保留歌曲名称"}, ensure_ascii=False)
    report = apply_model_proposals(response, repo=repo, allow_categories=["style"], task_id="seed", knowledge_read_rev=repo.rev)
    assert report.rev is not None, report.to_dict()


def rendered_handles(root, name="字幕风格"):
    from finesub.llm.knowledge.node.render import HandleMap

    repo = KnowledgeRepo.open(root)
    subject = repo.resolve_qualified(f"style/{name}")
    handles = HandleMap()
    repo.entry_prompt_text(subject.subject_id, handles=handles)
    handle = next(key for key, (node_id, _version) in handles.nodes.items()
                  if repo.store.node(node_id).payload.get("text") == "保留歌曲名称")
    return handles, handle, repo.rev


def fake_generation(monkeypatch, *, content, bindings, rev, after_call=lambda: None):
    calls = []
    @contextmanager
    def route(values):
        yield TaskRequest.model_validate(values), SimpleNamespace(source="agent", targets=["frozen-model"])
    class Client:
        def complete(self, *_args, **_kwargs):
            calls.append(content)
            return SimpleNamespace(content=content)
    def update(**kwargs):
        kwargs["client"].complete(None, [], agent_task_extras={
            "knowledge_identity": f"rev:{rev}", "kb_handle_bindings": bindings, "kb_signal_window": "chunk-1",
        })
        after_call()
        return {"mode": "refined_aligned", "chunks": [{"chunk": 1, "window_ids": ["all"], "proposal_text": content}]}
    monkeypatch.setattr(workflow, "_route", route)
    monkeypatch.setattr("finesub.llm.client.RoleClient", Client)
    monkeypatch.setattr("finesub.llm.knowledge.update.run_knowledge_update", update)
    return calls


def payload(paths, refined, **request):
    return {"final_srt": str(paths["final_srt"]), "refined_srt": str(refined), "task_id": "original-task",
            "request": {"input": "video", "style_mode": "update", **request}}


def test_material_capture_uses_core_multilingual_windows_and_detects_edits(tmp_path):
    paths, refined = task_files(tmp_path)
    before = feedback.capture_materials(paths, refined)
    assert before["mode"] == "refined_aligned"
    assert "初音未来" in before["windows"]["all"]["refined_csv"]
    refined.write_text("1\n00:00:00,000 --> 00:00:01,000\n人工润色\n", encoding="utf-8")
    assert feedback.capture_materials(paths, refined)["fingerprint"] != before["fingerprint"]


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 task-pinned auto style")
def test_auto_style_inherits_context_over_artifacts_and_filters_retired_write_target(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root, "风格甲")
    add_style(root, "风格乙")
    paths, _refined = task_files(tmp_path)
    paths["artifact_dir"].mkdir()
    rev = KnowledgeRepo.open(root).rev
    choice = {"outcome": "selected", "key": "风格乙", "rev": rev, "reason": "原任务选择"}
    paths["research_context"].write_text(json.dumps({"style_selection": choice}), encoding="utf-8")
    (paths["artifact_dir"] / "task-artifacts.jsonl").write_text(json.dumps({"kind": "style_selection", "payload": {
        **choice, "key": "风格甲"}}) + "\n", encoding="utf-8")
    request = TaskRequest(input="video", style_mode="update")
    names, metadata = feedback.task_style(request, root, paths)
    assert names == ("style/风格乙",)
    assert metadata["style_read_rev"] == rev
    _dispatch({"action": "maintenance", "command": "retire", "args": ["style/风格乙"]})
    names, metadata = feedback.task_style(request, root, paths)
    assert names == () and metadata["style_names"] == ["style/风格乙"]
    assert "style_warning" in metadata


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 retained auto style")
def test_cleanup_retains_task_style_without_retaining_bulk_artifacts(tmp_path, monkeypatch):
    from desktop.backend.worker.main import cleanup_task_intermediates

    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root)
    paths, _refined = task_files(tmp_path)
    paths["artifact_dir"].mkdir()
    rev = KnowledgeRepo.open(root).rev
    choice = {"outcome": "selected", "key": "字幕风格", "rev": rev, "reason": "原任务选择"}
    (paths["artifact_dir"] / "task-artifacts.jsonl").write_text(
        json.dumps({"kind": "style_selection", "payload": choice}, ensure_ascii=False) + "\n", encoding="utf-8")
    (paths["artifact_dir"] / "bulky-session.json").write_text("{}", encoding="utf-8")
    cleanup_task_intermediates(paths["final_srt"], preserve=[paths["final_srt"]])
    assert not paths["artifact_dir"].exists()
    assert paths["stable_json"].is_file() and paths["annotated_csv"].is_file()
    assert json.loads(feedback.retained_style_path(paths["final_srt"]).read_text(encoding="utf-8"))["key"] == "字幕风格"
    names, metadata = feedback.task_style(TaskRequest(input="video", style_mode="update"), root, paths)
    assert names == ("style/字幕风格",) and metadata["style_read_rev"] == rev

    # A later core-owned record takes precedence over an older desktop copy.
    paths["research_context"].parent.mkdir(parents=True, exist_ok=True)
    paths["research_context"].write_text(json.dumps({"style_selection": {
        "outcome": "none", "rev": rev, "reason": "本次不用风格"}}), encoding="utf-8")
    names, metadata = feedback.task_style(TaskRequest(input="video", style_mode="update"), root, paths)
    assert names == () and metadata["style_names"] == []


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 retained auto style")
@pytest.mark.parametrize("failure", [OSError("disk full"), RuntimeError("record unavailable")])
def test_retention_failure_keeps_original_artifacts_without_failing_task(tmp_path, monkeypatch, caplog, failure):
    from desktop.backend.worker.main import cleanup_task_intermediates

    paths, _refined = task_files(tmp_path)
    paths["artifact_dir"].mkdir()
    paths["research_context"].write_text(json.dumps({"style_selection": {
        "outcome": "none", "rev": 0}}), encoding="utf-8")
    def fail(*_args, **_kwargs):
        raise failure
    monkeypatch.setattr("finesub_bootstrap.fsops.write_atomic", fail)
    cleanup_task_intermediates(paths["final_srt"])
    assert paths["artifact_dir"].is_dir()
    assert paths["research_context"].is_file() and paths["final_srt"].is_file()
    assert not feedback.retained_style_path(paths["final_srt"]).exists()
    assert "kept intermediates" in caplog.text


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 retained auto style")
@pytest.mark.parametrize("saved", ["[", "[]"])
def test_corrupt_retained_style_refuses_feedback_without_picking_another_style(tmp_path, monkeypatch, saved):
    root = knowledge_root(tmp_path, monkeypatch)
    paths, _refined = task_files(tmp_path)
    feedback.retained_style_path(paths["final_srt"]).write_text(saved, encoding="utf-8")
    with pytest.raises(ValueError):
        feedback.task_style(TaskRequest(input="video", style_mode="update"), root, paths)


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 style marks")
def test_apply_books_frozen_style_evidence_once_without_rereading_edited_srt(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root)
    paths, refined = task_files(tmp_path)
    handles, handle, rev = rendered_handles(root)
    content = f"<knowledge_proposals></knowledge_proposals>\n<style_marks>\n{handle}|confirmed|0.0|精修保留\n</style_marks>"
    calls = fake_generation(monkeypatch, content=content, bindings=handles.bindings(), rev=rev)
    draft = workflow.generate_refined(root, payload(paths, refined, style="style/字幕风格"))
    assert draft["has_feedback_evidence"] is True
    assert "refined_evidence" not in draft and "bindings" not in draft["chunks"][0]
    repo = KnowledgeRepo.open(root)
    assert repo.store.conn.execute("SELECT COUNT(*) FROM evidence WHERE evidence_kind='judged'").fetchone()[0] == 0
    refined.write_text("1\n00:00:00,500 --> 00:00:01,000\n后来改过的字幕\n", encoding="utf-8")
    result = workflow.apply_draft(root, draft["draft_id"])
    assert result["status"] == "evidence_only", result
    assert result["apply_reports"][0]["style_marks"]["booked"] == 1
    assert workflow.apply_draft(root, draft["draft_id"])["status"] == "already_applied"
    assert repo.store.conn.execute("SELECT COUNT(*) FROM evidence WHERE evidence_kind='judged'").fetchone()[0] == 1
    assert len(calls) == 1


def test_refinement_comparison_is_frozen_and_only_written_after_apply(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    paths, refined = task_files(tmp_path)
    calls = fake_generation(monkeypatch, content="<knowledge_proposals></knowledge_proposals>", bindings=[], rev=KnowledgeRepo.open(root).rev)
    seen = []
    def evidence(_store, windows, **kwargs):
        seen.extend(list(windows))
        assert kwargs["task_id"] == "original-task"
        return (1, 0)
    monkeypatch.setattr("finesub.llm.knowledge.node.signals.refined_alignment_evidence", evidence)
    draft = workflow.generate_refined(root, payload(paths, refined, style_mode="none"))
    assert not seen
    refined.unlink()
    assert workflow.apply_draft(root, draft["draft_id"])["status"] == "evidence_only"
    assert len(seen) == 1 and "初音未来" in seen[0][3]
    assert len(calls) == 1


def test_edit_during_generation_refuses_draft_and_never_books_evidence(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    before = KnowledgeRepo.open(root).store.conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    paths, refined = task_files(tmp_path)
    fake_generation(monkeypatch, content="<knowledge_proposals></knowledge_proposals>", bindings=[],
        rev=KnowledgeRepo.open(root).rev, after_call=lambda: refined.write_text("1\n00:00:00,000 --> 00:00:01,000\n已修改\n", encoding="utf-8"))
    with pytest.raises(ValueError, match="materials changed"):
        workflow.generate_refined(root, payload(paths, refined, style_mode="none"))
    assert not (root.parent / "knowledge-proposals").exists()
    assert KnowledgeRepo.open(root).store.conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == before


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 style marks")
def test_evidence_receipt_recovers_after_commit_and_deduplicates(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root)
    paths, refined = task_files(tmp_path)
    handles, handle, rev = rendered_handles(root)
    proposal = json.dumps({"op": "append_lines", "category": "common", "entry": "作品", "section": "档案", "content": "[译名] 初音未来"}, ensure_ascii=False)
    content = f"<knowledge_proposals>{proposal}</knowledge_proposals>\n<style_marks>{handle}|confirmed|0.0|精修保留</style_marks>"
    calls = fake_generation(monkeypatch, content=content, bindings=handles.bindings(), rev=rev)
    draft = workflow.generate_refined(root, payload(paths, refined, style="style/字幕风格"))
    save = workflow._save
    def crash(path, saved):
        if saved.get("apply_reports"):
            raise RuntimeError("exit before receipt")
        save(path, saved)
    monkeypatch.setattr(workflow, "_save", crash)
    with pytest.raises(RuntimeError, match="before receipt"):
        workflow.apply_draft(root, draft["draft_id"])
    monkeypatch.setattr(workflow, "_save", save)
    recovered = workflow.apply_draft(root, draft["draft_id"])
    assert recovered["status"] == "applied", recovered
    assert recovered["apply_reports"][0]["recovered"]
    assert recovered["apply_reports"][0]["style_marks"]["duplicates"] == 1
    assert KnowledgeRepo.open(root).store.conn.execute("SELECT COUNT(*) FROM evidence WHERE evidence_kind='judged'").fetchone()[0] == 1
    assert len(calls) == 1


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 style marks")
def test_invalid_marks_are_dropped_not_applied_to_other_times_or_handles(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root)
    paths, refined = task_files(tmp_path)
    handles, handle, rev = rendered_handles(root)
    content = f"<knowledge_proposals></knowledge_proposals>\n<style_marks>\n{handle}|confirmed|9.0|其他窗口\n@unknown|refuted|0.0|无效句柄\n</style_marks>"
    fake_generation(monkeypatch, content=content, bindings=handles.bindings(), rev=rev)
    draft = workflow.generate_refined(root, payload(paths, refined, style="style/字幕风格"))
    result = workflow.apply_draft(root, draft["draft_id"])
    assert result["status"] == "no_change"
    assert len(result["apply_reports"][0]["style_marks"]["dropped"]) == 2


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 style marks")
def test_evidence_failure_does_not_undo_committed_knowledge(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root)
    paths, refined = task_files(tmp_path)
    handles, handle, rev = rendered_handles(root)
    proposal = json.dumps({"op": "append_lines", "category": "common", "entry": "作品", "section": "档案", "content": "[译名] 初音未来"}, ensure_ascii=False)
    fake_generation(monkeypatch, content=f"<knowledge_proposals>{proposal}</knowledge_proposals>", bindings=handles.bindings(), rev=rev)
    draft = workflow.generate_refined(root, payload(paths, refined, style="style/字幕风格"))
    def fail(*args, **kwargs):
        raise OSError("evidence disk error")
    monkeypatch.setattr("finesub.llm.knowledge.style_marks.book_style_marks", fail)
    result = workflow.apply_draft(root, draft["draft_id"])
    assert result["status"] == "applied"
    assert any("evidence disk error" in warning for warning in result["warnings"])
    assert KnowledgeRepo.open(root).rev == rev + 1


def test_empty_entry_proposal_with_stale_revision_cannot_book_feedback(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    draft = workflow._draft(root, [], {"refined_evidence": [{"chunk_id": "frozen"}], "evidence_task_id": "task"})
    _dispatch({"action": "maintenance", "command": "new", "args": ["common", "另一个作品", "--intro", "作品", "--type", "其他"]})
    def must_not_book(*args):
        raise AssertionError("stale draft reached evidence writer")
    monkeypatch.setattr(workflow, "book_refined_evidence", must_not_book)
    with pytest.raises(ValueError, match="Knowledge changed"):
        workflow.apply_draft(root, draft["draft_id"])


def test_refinement_proposal_cannot_write_a_different_style(tmp_path, monkeypatch):
    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root)
    add_style(root, "另一套风格")
    paths, refined = task_files(tmp_path)
    rev = KnowledgeRepo.open(root).rev
    proposal = json.dumps({"op": "append_lines", "category": "style", "entry": "另一套风格",
        "section": "约定", "content": "[标点] 使用中文标点"}, ensure_ascii=False)
    fake_generation(monkeypatch, content=f"<knowledge_proposals>{proposal}</knowledge_proposals>", bindings=[], rev=rev)
    with pytest.raises(ValueError, match="task-pinned style"):
        workflow.generate_refined(root, payload(paths, refined, style="style/字幕风格"))
    assert KnowledgeRepo.open(root).rev == rev


def test_real_core_update_generation_freezes_its_actual_window_bindings(tmp_path, monkeypatch):
    from finesub.llm.client import LLMCallResult
    from finesub.llm.token_budget import HeuristicTokenCounter

    root = knowledge_root(tmp_path, monkeypatch)
    add_style(root)
    paths, refined = task_files(tmp_path)
    calls = []
    @contextmanager
    def route(values):
        yield TaskRequest.model_validate(values), SimpleNamespace(source="offline", targets=[])
    class Client:
        def complete(self, *_args, **kwargs):
            calls.append(kwargs)
            extras = kwargs["agent_task_extras"]
            repo = KnowledgeRepo.open(root)
            from finesub.llm.knowledge.node.render import HandleMap
            handles = HandleMap()
            handles.seed(extras["kb_handle_bindings"])
            handle = next(key for key, (node_id, _version) in handles.nodes.items()
                if repo.store.node(node_id).payload.get("text") == "保留歌曲名称")
            text = f'<knowledge_proposals></knowledge_proposals>\n<style_marks>{handle}|confirmed|0.0|精修保留</style_marks>'
            return LLMCallResult(content=text, role=_args[0], model="offline-fake", fallback_used=False, raw_response={})
    monkeypatch.setattr(workflow, "_route", route)
    monkeypatch.setattr("finesub.llm.client.RoleClient", Client)
    monkeypatch.setattr("finesub.llm.knowledge.update.default_token_counter", lambda **kwargs: HeuristicTokenCounter())
    before = KnowledgeRepo.open(root).rev
    draft = workflow.generate_refined(root, payload(paths, refined, style="style/字幕风格"))
    assert draft["mode"] == "refined_aligned" and draft["chunks"]
    assert len(calls) == 1
    assert KnowledgeRepo.open(root).rev == before
    result = workflow.apply_draft(root, draft["draft_id"])
    assert result["status"] == ("evidence_only" if unified_llm_contract() else "no_change"), result
    assert len(calls) == 1
