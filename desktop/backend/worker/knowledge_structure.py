"""Human structural changes use the core proposal translator and apply engine."""
from __future__ import annotations

import json
from pathlib import Path
import uuid

from desktop.backend.worker.knowledge_workflow import _path, _save


def structure(root: Path, payload: dict) -> dict:
    from finesub.llm.knowledge.base import knowledge_write_lock
    from finesub.llm.knowledge.node.apply import apply_envelope
    from finesub.llm.knowledge.node.envelope import Binding, Envelope
    from finesub.llm.knowledge.node.presets import CATEGORIES
    from finesub.llm.knowledge.node.proposals import translate_model_proposals
    from finesub.llm.knowledge.node.repo import KnowledgeRepo

    with knowledge_write_lock(root) as locked:
        if not locked:
            raise ValueError("知识库正在使用 / Knowledge is busy")
        repo = KnowledgeRepo.open(root)
        if payload.get("apply"):
            path = _path(root, payload.get("draft_id", ""))
            draft = json.loads(path.read_text(encoding="utf-8"))
            if draft.get("kind") != "human-structure":
                raise ValueError("Not a structural preview")
            if draft.get("result"):
                return {**draft["result"], "already_applied": True}
            if repo.rev != draft["expected_rev"]:
                raise ValueError("知识库已变化，请重新预览 / Knowledge changed; preview again")
            envelope = Envelope.from_dict(draft["envelope"])
            result = apply_envelope(repo.store, envelope, revision_kind="user", note="desktop:structure")
            if result.rolled_back:
                raise ValueError(f"Structure rolled back: {result.rollback_reason}")
            outcome = {"revision": result.rev, "applied": len(result.applied_ops),
                "rejected": [str(reason) for _, reason in result.rejected_ops], "warnings": []}
            try:
                repo.refresh_rendered()
            except (OSError, ValueError) as error:
                outcome["warnings"].append(f"更改已提交，阅读投影刷新失败 / Changes committed; projection refresh failed: {error}")
            try:
                _save(path, {**draft, "result": outcome})
            except OSError as error:
                outcome["warnings"].append(f"更改已提交，回执未保存；请刷新核查 / Changes committed; receipt not saved: {error}")
            return outcome
        if repo.rev != payload.get("expected_rev"):
            raise ValueError("知识库已变化，请刷新 / Knowledge changed; refresh first")
        entry, section = payload.get("entry", ""), payload.get("section", "").strip()
        if not section or len(section) > 200:
            raise ValueError("请选择一个小节 / Choose a section")
        operation = payload.get("operation")
        bindings = []
        def bind(name, handle):
            resolved = repo.resolve_qualified(name)
            if resolved is None:
                raise ValueError(f"Unknown entry: {name}")
            node = repo.store.node(resolved.subject_id)
            bindings.append(Binding(handle=handle, kind="node", id=node.local_id,
                expected_valid_from_rev=node.valid_from_rev))
            return handle
        source = bind(entry, "@source")
        if operation == "split":
            if not payload.get("intro", "").strip():
                raise ValueError("请填写子条目简介 / Enter a sub-entry introduction")
            proposal = {"op": "split_entry", "entry": source, "section": section, "intro": payload["intro"]}
        elif operation == "move":
            proposal = {"op": "move_line", "entry": source, "from_section": section,
                "to_entry": bind(payload.get("to_entry", ""), "@destination"), "section": payload.get("target_section") or section}
        else:
            raise ValueError("Unsupported structural operation")
        proposal["reason"] = "desktop human structural change"
        ops, report, _, bindings = translate_model_proposals([proposal], repo=repo,
            knowledge_read_rev=repo.rev, bindings=bindings, allow_categories=CATEGORIES)
        skipped = [record.reason for record in report.skipped]
        if not ops or skipped:
            raise ValueError("; ".join(skipped) or "没有可执行的结构变化 / No structural changes")
        ops = [{key: value for key, value in op.items() if key != "_meta"} for op in ops]
        identifier = uuid.uuid4().hex
        envelope = Envelope(task_id=f"desktop-structure-{identifier}", assignment_id="desktop-human",
            context_epoch=0, knowledge_read_rev=repo.rev, ops=ops, handle_bindings=bindings,
            draft_bindings=sorted({op["handle"] for op in ops if op.get("op") == "create" and op.get("handle")}))
        _save(_path(root, identifier), {"kind": "human-structure", "expected_rev": repo.rev,
            "envelope": envelope.to_dict(), "proposal": proposal})
        return {"draft_id": identifier, "expected_rev": repo.rev, "operations": ops, "proposal": proposal}
