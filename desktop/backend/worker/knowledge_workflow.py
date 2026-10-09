"""Desktop review drafts; FineSub remains the only knowledge write engine."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from desktop.backend.common.models import TaskRequest


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _path(root: Path, draft_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", draft_id):
        raise ValueError("Invalid proposal ID / 无效的提案编号")
    return root.parent / "knowledge-proposals" / f"{draft_id}.json"


def _read_srt(path: str, encoding: str) -> tuple[list, str, str]:
    from finesub.subtitles.model import parse_srt

    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".srt" or source.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("请选择不超过 8 MB 的 SRT / Choose an SRT smaller than 8 MB")
    data = source.read_bytes()
    if encoding == "auto":
        encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    if encoding not in {"utf-8-sig", "utf-16", "gb18030", "cp932"}:
        raise ValueError("Unsupported subtitle encoding")
    try:
        segments = parse_srt(data.decode(encoding, errors="strict"))
    except UnicodeError as error:
        raise ValueError("字幕编码不匹配，请选择 GB18030 或 CP932 后重试 / Select the correct encoding") from error
    if not segments or len(segments) > 10000:
        raise ValueError("SRT must contain 1–10000 cues / 字幕条数必须为 1–10000")
    for row in segments:
        if row.end <= row.start or not row.text.strip() or "\ufffd" in row.text or "\x00" in row.text:
            raise ValueError(f"Invalid subtitle cue / 无效字幕：{row.index}")
    return segments, encoding, hashlib.sha256(data).hexdigest()


def inspect_pair(payload: dict) -> dict:
    original, source_encoding, source_hash = _read_srt(payload["source_srt"], payload.get("source_encoding", "auto"))
    refined, refined_encoding, refined_hash = _read_srt(payload["refined_srt"], payload.get("refined_encoding", "auto"))
    if len(original) != len(refined):
        raise ValueError(f"字幕条数不一致 / Cue counts differ: {len(original)} ≠ {len(refined)}")
    pairs = []
    for position, (left, right) in enumerate(zip(original, refined), 1):
        if (round(left.start * 1000), round(left.end * 1000)) != (round(right.start * 1000), round(right.end * 1000)):
            raise ValueError(f"第 {position} 条时间轴不一致 / Timing mismatch at cue {position}")
        pairs.append({"cue": position, "start_ms": round(left.start * 1000), "end_ms": round(left.end * 1000), "original": left.text, "refined": right.text})
    return {"count": len(pairs), "source_encoding": source_encoding, "refined_encoding": refined_encoding,
            "source_hash": source_hash, "refined_hash": refined_hash, "pairs": pairs}


@contextmanager
def _route(values: dict):
    from desktop.backend.worker.model_source import source_route
    from desktop.backend.worker.knowledge_main import _routing_override

    request = TaskRequest.model_validate(values).model_copy(update={"stage": "final-srt", "llm_media": "text", "llm_correction_media": "text", "llm_planning_media": "text"})
    with source_route(request) as route:
        if route.skip_reason:
            raise ValueError(f"没有可用模型 / No available model: {route.skip_reason}")
        with _routing_override(route.models):
            yield request, route


def _draft(root: Path, chunks: list[dict], metadata: dict) -> dict:
    from finesub.llm.knowledge.node.proposals import parse_model_proposals

    if len({chunk["read_rev"] for chunk in chunks}) > 1:
        raise ValueError("生成期间知识库已变化，请重新生成 / Knowledge changed during generation")
    draft_id = uuid.uuid4().hex
    result = {**metadata, "draft_id": draft_id, "status": "generated", "chunks": chunks,
              "proposal_count": sum(len(parse_model_proposals(chunk["proposal_text"])) for chunk in chunks)}
    _save(_path(root, draft_id), result)
    return result


class CapturingClient:
    def __init__(self, client):
        self.client = client
        self.calls: list[dict] = []

    def __getattr__(self, key):
        return getattr(self.client, key)

    def complete(self, *args, **kwargs):
        result = self.client.complete(*args, **kwargs)
        extra = kwargs.get("agent_task_extras") or {}
        self.calls.append({"proposal_text": result.content, "bindings": extra.get("kb_handle_bindings", []),
                           "read_rev": int(extra["knowledge_identity"].split(":")[-1]),
                           "window": extra.get("kb_signal_window")})
        return result


def generate_refined(root: Path, payload: dict) -> dict:
    from finesub.llm.client import RoleClient
    from finesub.llm.knowledge.style import resolve_style_selection
    from finesub.llm.knowledge.update import derive_task_paths, run_knowledge_update

    values = dict(payload.get("request") or {"input": payload["final_srt"], "llm_model": payload.get("llm_model", [])})
    if payload.get("llm_model"):
        values["llm_model"] = payload["llm_model"]
    with _route(values) as (request, route):
        style = resolve_style_selection(request.style, request.style_mode, knowledge_root=root, difficulty=request.llm_difficulty)
        client = CapturingClient(RoleClient())
        report = run_knowledge_update(final_srt=payload["final_srt"], refined_srt=payload["refined_srt"],
            artifact_dir=derive_task_paths(payload["final_srt"])["artifact_dir"], task_id=payload["task_id"],
            task_summary=payload.get("task_summary", ""), knowledge_root=root, execute=True, apply=False,
            resume=payload.get("resume", True), client=client, difficulty=request.llm_difficulty,
            style_names=style.names if style.mode == "update" else ())
        chunks = []
        for chunk in report.get("chunks", []):
            text = chunk.get("proposal_text")
            if not text:
                continue
            match = next((call for call in reversed(client.calls) if call["proposal_text"] == text and call["window"] == f"chunk-{chunk['chunk']}"), None)
            if match is None:
                raise RuntimeError("Cannot freeze proposal bindings")
            chunks.append({**match, "allow_categories": ["common", "streamer"] + (["style"] if style.mode == "update" else [])})
        return _draft(root, chunks, {"mode": report.get("mode"), "warnings": report.get("warnings", []),
            "skipped": report.get("skipped"), "source": route.source, "models": list(route.targets or request.llm_model),
            "style_names": list(style.names), "style_mode": style.mode})


def generate_pair(root: Path, payload: dict) -> dict:
    from finesub.llm.client import RoleClient
    from finesub.llm.knowledge.node.repo import KnowledgeRepo
    from finesub.llm.knowledge.node.render import HandleMap
    from finesub.llm.knowledge.node.repair import render_repair_prompt, REPAIR_MAX_TOKENS
    from finesub.llm.knowledge.node.proposals import parse_model_proposals
    from finesub.llm.knowledge.node.proposals import translate_model_proposals
    from finesub.llm.knowledge.node.envelope import Binding
    from finesub.llm.routing.config import LLMRole, planning_limits_for
    from finesub.llm.token_budget import HeuristicTokenCounter

    pair = inspect_pair(payload)
    values = dict(payload["request"])
    values["input"] = payload["source_srt"]
    with _route(values) as (request, route):
        repo = KnowledgeRepo.open(root)
        chunks = []
        counter = HeuristicTokenCounter()
        limit = planning_limits_for("knowledge", request.llm_difficulty).prompt_input_limit
        client = RoleClient()
        targets = list(dict.fromkeys(filter(None, [payload["subject"], payload.get("style_subject", "")])))
        for name in targets:
            target = repo.resolve_qualified(name)
            if target is None:
                raise ValueError(f"知识条目不存在 / Entry not found: {name}")
            pending = [pair["pairs"]]
            while pending:
                rows = pending.pop(0)
                handles = HandleMap()
                prompt = render_repair_prompt(repo, target.subject_id, handles=handles,
                    material=json.dumps({"evidence_kind": "human_aligned_subtitle_translation", "asr_evidence": False, "pairs": rows}, ensure_ascii=False),
                    user_prompt=payload.get("prompt", ""))
                if counter.count_text(prompt) > limit:
                    if len(rows) == 1:
                        raise ValueError("条目或单条字幕超出模型窗口 / Entry or cue exceeds model window")
                    middle = len(rows) // 2
                    pending[:0] = [rows[:middle], rows[middle:]]
                    continue
                rev = repo.rev
                response = client.complete(LLMRole.GENERAL_CAPABLE, [{"role": "user", "content": prompt}],
                    max_tokens=REPAIR_MAX_TOKENS, task_group="knowledge", difficulty=request.llm_difficulty,
                    agent_task_extras={"knowledge_root": str(root), "knowledge_identity": f"rev:{rev}",
                        "kb_tools": "propose", "kb_handle_bindings": handles.bindings(), "kb_signal_task": "desktop-bilingual"})
                # Ingest is one named entry, never an implicit rename/retirement or new subject.
                for proposal in parse_model_proposals(response.content):
                    if proposal.get("op") not in {"append_lines", "update", "add_item", "remove_item"}:
                        raise ValueError("导入提案包含不支持的操作，请重新生成 / Unsupported import operation")
                    entry = proposal.get("entry")
                    if entry and entry not in {target.key, name, next((key for key, value in handles.nodes.items() if value[0] == target.subject_id), "")}:
                        raise ValueError("提案超出所选条目 / Proposal exceeds selected entry")
                ops, _, _, _ = translate_model_proposals(parse_model_proposals(response.content), repo=repo,
                    knowledge_read_rev=rev, bindings=[Binding(**binding) for binding in handles.bindings()],
                    allow_categories=[target.category])
                for op in ops:
                    record = op.get("_meta", {}).get("record")
                    if record and (record.category, record.entry) != (target.category, target.key):
                        raise ValueError("提案超出所选条目 / Proposal exceeds selected entry")
                    if op.get("field") == "misheard":
                        raise ValueError("双语导入不能写入 ASR 误听证据 / Subtitle pairs cannot establish ASR errors")
                chunks.append({"proposal_text": response.content, "bindings": handles.bindings(), "read_rev": rev,
                    "allow_categories": [target.category], "subject": name})
        return _draft(root, chunks, {"mode": "bilingual_ingest", "count": pair["count"],
            "source_hash": pair["source_hash"], "refined_hash": pair["refined_hash"],
            "source": route.source, "models": list(route.targets or request.llm_model), "targets": targets,
            "warnings": ["双语文本是术语与表达风格材料，不是 ASR 误听证据 / Text pairs are not ASR error evidence"]})


def apply_draft(root: Path, draft_id: str) -> dict:
    from finesub.llm.knowledge.base import knowledge_write_lock
    from finesub.llm.knowledge.node.repo import KnowledgeRepo
    from finesub.llm.knowledge.node.render import HandleMap
    from finesub.llm.knowledge.node.proposals import apply_model_proposals

    path = _path(root, draft_id)
    with knowledge_write_lock(root) as locked:
        if not locked:
            raise ValueError("知识库正在写入，请稍后重试 / Knowledge base is busy")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if "result" in saved:
            return {**saved["result"], "status": "already_applied"}
        repo = KnowledgeRepo.open(root)
        reports = saved.setdefault("apply_reports", [])
        expected = saved.get("expected_rev", saved["chunks"][0]["read_rev"] if saved["chunks"] else repo.rev)
        # A durable core revision identifies a commit even if the desktop exits before saving its receipt.
        next_index = len(reports)
        if next_index < len(saved["chunks"]):
            chunk = saved["chunks"][next_index]
            digest = hashlib.sha256(chunk["proposal_text"].encode()).hexdigest()
            recovered = [repo.store.revision(rev) for rev in range(expected + 1, repo.rev + 1)]
            if len(recovered) == 1 and recovered[0].task_id == f"desktop-{draft_id}-{next_index}" and recovered[0].note == f"proposal_text:{digest}":
                reports.append({"rev": recovered[0].rev, "recovered": True, "applied": [], "skipped": []})
                expected = repo.rev
        if repo.rev != expected:
            raise ValueError("知识库已变化，请重新生成提案 / Knowledge changed; regenerate the proposal")
        for index in range(len(reports), len(saved["chunks"])):
            chunk = saved["chunks"][index]
            handles = HandleMap()
            handles.seed(chunk["bindings"])
            report = apply_model_proposals(chunk["proposal_text"], repo=repo, handles=handles,
                allow_categories=chunk["allow_categories"], task_id=f"desktop-{draft_id}-{index}",
                knowledge_read_rev=chunk["read_rev"], proposal_text_hash=hashlib.sha256(chunk["proposal_text"].encode()).hexdigest()).to_dict()
            reports.append(report)
            saved["expected_rev"] = repo.rev
            _save(path, saved)
            if report.get("rolled_back"):
                break
        committed = sum(report.get("rev") is not None for report in reports)
        issues = sum(bool(report.get("rolled_back") or report.get("skipped") or report.get("conflicts")) for report in reports)
        result = {"draft_id": draft_id, "status": "partial" if committed and issues else "applied" if committed else "blocked" if issues else "no_change",
                  "committed_chunks": committed, "revision": repo.rev, "apply_reports": reports}
        saved["result"] = result
        _save(path, saved)
        return result
