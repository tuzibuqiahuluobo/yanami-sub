"""Freeze task feedback for review; the core owns style and evidence rules."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from desktop.backend.common.core_compat import unified_llm_contract


def retained_style_path(final_srt):
    final = Path(final_srt)
    return final.with_name(f"{final.stem}-style-selection.json")


def retain_task_style(final_srt):
    if not unified_llm_contract():
        return
    from finesub.llm.correction_translation import _recorded_style_choice
    from finesub.llm.knowledge.update import derive_task_paths
    from finesub_bootstrap.fsops import write_atomic

    paths = derive_task_paths(final_srt)
    choice = _recorded_style_choice(context_path=paths["research_context"], artifact_dir=paths["artifact_dir"])
    if choice is not None:
        write_atomic(retained_style_path(paths["final_srt"]), json.dumps(choice.to_dict(), ensure_ascii=False) + "\n")


def task_style(request, root, paths):
    from finesub.llm.knowledge.style import resolve_style_selection

    selection = resolve_style_selection(request.style, request.style_mode,
        knowledge_root=root, difficulty=request.llm_difficulty)
    names = selection.names if selection.mode == "update" else ()
    metadata = {"style_names": list(selection.names), "style_mode": selection.mode,
                "style_read_rev": getattr(selection, "rev", None)}
    if unified_llm_contract() and getattr(selection, "auto", False):
        from finesub.llm.correction_translation import _recorded_style_choice, _writable_style_names
        from finesub.llm.knowledge.style import StyleChoice, load_style_catalog

        choice = _recorded_style_choice(context_path=paths["research_context"], artifact_dir=paths["artifact_dir"])
        if choice is None and retained_style_path(paths["final_srt"]).is_file():
            # Live core records win; this small desktop sidecar survives the
            # deliberately removable LLM checkpoint/session directory.
            saved = json.loads(retained_style_path(paths["final_srt"]).read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                raise ValueError("任务风格记录损坏 / Invalid retained task style record")
            choice = StyleChoice.from_dict(saved)
            selection = selection.resolved(choice.names, rev=choice.rev)
        names = _writable_style_names(selection, load_style_catalog(root),
            context_path=paths["research_context"], artifact_dir=paths["artifact_dir"])
        metadata.update(style_names=list(choice.names) if choice else [],
            style_read_rev=choice.rev if choice else None,
            style_selection=choice.to_dict() if choice else None)
        if selection.mode == "update" and (choice is None or (choice.names and not names)):
            metadata["style_warning"] = (
                "原任务没有可写的风格选择记录，本次不重新选风格或写入其他风格。 / "
                "No writable task-pinned style; no new style will be selected."
            )
    return names, metadata


def capture_materials(paths, refined_srt):
    from finesub.llm.knowledge.materials import build_knowledge_materials

    # This pass collects windows only; actual model chunking stays core-owned.
    materials = build_knowledge_materials(stable_json=paths["stable_json"],
        annotated_csv=paths["annotated_csv"], final_srt=paths["final_srt"],
        research_context=paths["research_context"], artifact_dirs=[paths["artifact_dir"]],
        refined_srt=refined_srt, count_tokens=lambda _text: 0)
    windows = {window.chunk_id: asdict(window) for chunk in materials.chunks for window in chunk.windows}
    semantic = {"mode": materials.mode, "windows": windows,
                "context": materials.general_context, "feedback": asdict(materials.feedback)}
    digest = hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return {"mode": materials.mode, "windows": windows, "fingerprint": digest}


def freeze_style_evidence(root, chunk, windows, style_names):
    if not unified_llm_contract() or not style_names:
        return None
    from finesub.llm.knowledge.node.repo import KnowledgeRepo
    from finesub.llm.knowledge.style_marks import refined_start_times

    subject = KnowledgeRepo.open(root).resolve_qualified(style_names[0], rev=chunk["read_rev"])
    if subject is None:
        raise ValueError("风格条目已变化，请重新生成 / Style changed; regenerate the proposal")
    return {"subject_id": subject.subject_id,
            "refined_starts": sorted(refined_start_times(window["refined_csv"] for window in windows))}


def validate_style_scope(root, chunk, style_names):
    if not style_names:
        return
    from finesub.llm.knowledge.node.envelope import Binding
    from finesub.llm.knowledge.node.proposals import parse_model_proposals, translate_model_proposals
    from finesub.llm.knowledge.node.repo import KnowledgeRepo

    repo = KnowledgeRepo.open(root)
    # The core updates at most the first named style, not every style category.
    selected = repo.resolve_qualified(style_names[0], rev=chunk["read_rev"])
    ops, _, _, _ = translate_model_proposals(parse_model_proposals(chunk["proposal_text"]), repo=repo,
        knowledge_read_rev=chunk["read_rev"], bindings=[Binding(**row) for row in chunk["bindings"]],
        allow_categories=chunk["allow_categories"])
    for op in ops:
        record = op.get("_meta", {}).get("record")
        if record and record.category == "style" and (selected is None or record.entry != selected.key):
            raise ValueError("提案超出本任务选中的风格条目 / Proposal exceeds the task-pinned style")


def book_refined_evidence(repo, saved):
    rows = saved.get("refined_evidence")
    if not rows:
        return {}
    try:
        from finesub.llm.knowledge.node.signals import refined_alignment_evidence
        confirmed, refuted = refined_alignment_evidence(repo.store,
            ((row["chunk_id"], row["raw_csv"], row["final_csv"], row["refined_csv"]) for row in rows),
            task_id=saved["evidence_task_id"])
        return {"confirmed": confirmed, "refuted": refuted}
    except Exception as error:  # Evidence is fail-soft, like the core update path.
        return {"error": f"{type(error).__name__}: {error}"}


def book_style_evidence(repo, chunk, task_id):
    frozen = chunk.get("style_evidence")
    if not frozen:
        return {}
    try:
        from finesub.llm.knowledge.node.render import HandleMap
        from finesub.llm.knowledge.style_marks import book_style_marks
        handles = HandleMap()
        handles.seed(chunk["bindings"])
        return book_style_marks(repo.store, chunk["proposal_text"], handles=handles,
            style_subject_id=frozen["subject_id"], refined_starts=set(frozen["refined_starts"]),
            read_rev=chunk["read_rev"], task_id=task_id)
    except Exception as error:  # A committed proposal must not become a failed task.
        return {"booked": 0, "duplicates": 0, "dropped": [], "error": f"{type(error).__name__}: {error}"}
