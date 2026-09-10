from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import asdict, is_dataclass
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
from typing import Any, Iterator, Mapping


_MAINTENANCE_COMMANDS = {
    "log",
    "show",
    "edit",
    "new",
    "retire",
    "revert",
    "restore",
    "refresh",
    "phase-b",
    "candidates",
    "verify",
    "repair",
    "ingest",
}
_SHARE_COMMANDS = {
    "register",
    "mark",
    "unmark",
    "push",
    "status",
    "pull",
    "conflicts",
    "review",
}


def _root() -> Path:
    value = os.environ.get("FINESUB_KNOWLEDGE_ROOT", "").strip()
    if not value:
        raise ValueError("FINESUB_KNOWLEDGE_ROOT is not configured")
    return Path(value).expanduser().resolve()


def _json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _queue_sort_key(row: Mapping[str, Any]) -> tuple[str, int]:
    """Keep a hand-edited/corrupt push ledger from breaking the whole page."""

    try:
        queue_id = int(row.get("queue_id") or 0)
    except (TypeError, ValueError):
        queue_id = 0
    return str(row.get("remote") or ""), queue_id


@contextmanager
def _routing_override(values: list[str]) -> Iterator[None]:
    from finesub.llm.routing.model_routes import (
        install_runtime_preferred,
        parse_llm_model_args,
        runtime_preferred,
    )

    previous = runtime_preferred()
    install_runtime_preferred(parse_llm_model_args(values))
    try:
        yield
    finally:
        install_runtime_preferred(previous)


def _snapshot() -> dict[str, Any]:
    from finesub.llm.knowledge.node.candidates import pending_human_reconciled
    from finesub.llm.knowledge.node.render import subject_aliases
    from finesub.llm.knowledge.node.repo import KnowledgeRepo
    from finesub.llm.knowledge.share.conflicts import describe, open_conflicts
    from finesub.llm.knowledge.share.cli import PUSH_LOG_FILENAME

    root = _root()
    repo = KnowledgeRepo.open(root)
    entries: list[dict[str, Any]] = []
    for subject in repo.subjects():
        payload = subject.payload
        category = str(payload.get("category") or "")
        surface = str(
            payload.get("surface")
            or payload.get("name")
            or subject.local_id
        )
        entries.append(
            {
                "id": subject.local_id,
                "qualified_name": f"{category}/{surface}" if category else surface,
                "key": surface,
                "category": category,
                "entry_type": str(payload.get("entry_type") or payload.get("type") or ""),
                "intro": str(payload.get("intro") or payload.get("description") or ""),
                "aliases": subject_aliases(repo.store, subject.local_id),
                "visibility": subject.visibility,
                "maturity": subject.maturity,
                "valid_from_rev": subject.valid_from_rev,
                "canonical_id": subject.canonical_id or "",
                "item_count": len(repo.store.items_of(subject.local_id)),
            }
        )
    entries.sort(key=lambda row: (row["category"], row["key"].casefold()))

    revisions = [
        dict(row)
        for row in repo.store.conn.execute(
            "SELECT rev, created_at, kind, task_id, note FROM revisions "
            "ORDER BY rev DESC LIMIT 100"
        ).fetchall()
    ]
    pending = pending_human_reconciled(repo.store)
    conflicts = []
    for row in open_conflicts(root):
        conflicts.append({**row, "description": describe(row)})

    remotes = []
    for row in repo.store.conn.execute(
        "SELECT key FROM meta WHERE key LIKE 'share:%:token' ORDER BY key"
    ).fetchall():
        key = str(row["key"])
        remotes.append(key[len("share:") : -len(":token")])

    pushes: list[dict[str, Any]] = []
    push_path = root / PUSH_LOG_FILENAME
    if push_path.is_file():
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for line in push_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except (TypeError, ValueError):
                continue
            if not isinstance(row, dict):
                continue
            identity = (
                str(row.get("remote") or ""),
                str(row.get("queue_id") or row.get("idempotency_key") or ""),
            )
            latest[identity] = row
        pushes = sorted(
            latest.values(),
            key=_queue_sort_key,
            reverse=True,
        )[:100]

    return {
        "root": str(root),
        "revision": repo.rev,
        "version": repo.version(),
        "entries": entries,
        "revisions": revisions,
        "pending_candidates": pending,
        "conflicts": conflicts,
        "registered_remotes": remotes,
        "pushes": pushes,
    }


def _entry(name: str, rev: int | None) -> dict[str, Any]:
    from finesub.llm.knowledge.node.repo import AmbiguousName, KnowledgeRepo

    repo = KnowledgeRepo.open(_root())
    subject = repo.store.node(name, rev)
    if subject is None:
        try:
            resolved = repo.resolve_qualified(name, rev)
        except AmbiguousName as error:
            raise ValueError(str(error)) from error
        if resolved is None:
            raise KeyError(f"no knowledge entry matches {name!r}")
        subject = repo.store.node(resolved.subject_id, rev)
    if subject is None:
        raise KeyError(f"knowledge entry {name!r} is unavailable at that revision")
    category = str(subject.payload.get("category") or "")
    key = str(subject.payload.get("surface") or subject.local_id)
    return {
        "id": subject.local_id,
        "qualified_name": f"{category}/{key}" if category else key,
        "key": key,
        "category": category,
        "revision": repo.rev if rev is None else rev,
        "valid_from_rev": subject.valid_from_rev,
        "text": repo.entry_text(subject.local_id, rev),
    }


def _run_cli(kind: str, command: str, args: list[str], content: str = "") -> dict[str, Any]:
    allowed = _MAINTENANCE_COMMANDS if kind == "maintenance" else _SHARE_COMMANDS
    if command not in allowed:
        raise ValueError(f"unsupported {kind} command: {command}")
    if any("\x00" in value for value in args):
        raise ValueError("command argument contains a NUL byte")

    if kind == "maintenance":
        from finesub.llm.knowledge import maintain as module
    else:
        from finesub.llm.knowledge.share import cli as module

    argv = ["--root", str(_root()), command, *args]

    def execute(cli_args: list[str]) -> tuple[int, str]:
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = int(module.main(cli_args))
            except SystemExit as error:
                code = int(error.code) if isinstance(error.code, int) else 1
                if isinstance(error.code, str):
                    print(error.code, file=stderr)
        rendered = "\n".join(
            part.strip()
            for part in (stdout.getvalue(), stderr.getvalue())
            if part.strip()
        )
        return code, rendered

    if kind == "maintenance" and command == "edit":
        if len(args) != 1:
            raise ValueError("edit requires exactly one entry name")
        with tempfile.TemporaryDirectory(prefix="finesub-desktop-kb-") as temporary:
            edit_file = Path(temporary) / "entry.md"
            edit_file.write_text(content, encoding="utf-8")
            exit_code, output = execute([*argv, "--file", str(edit_file)])
    else:
        exit_code, output = execute(argv)
    if exit_code:
        raise RuntimeError(output or f"{kind} command failed with exit code {exit_code}")
    return {"command": command, "exit_code": exit_code, "output": output}


def _feedback(final_srt: str) -> dict[str, Any]:
    from finesub.llm.knowledge.feedback import aggregate_task_update_feedback
    from finesub.llm.knowledge.update import derive_task_paths

    artifact_dir = derive_task_paths(final_srt)["artifact_dir"]
    aggregate = aggregate_task_update_feedback([artifact_dir])
    windows = []
    for chunk_id, feedback in aggregate.window_feedback.items():
        windows.append(
            {
                "chunk_id": chunk_id,
                "hints": [hint.to_dict() for hint in feedback.hints],
                "asr_corrections": list(feedback.asr_corrections),
                "uncertainties": list(feedback.uncertainties),
                "warnings": list(feedback.warnings),
                "retrieval_urls": list(feedback.retrieval_urls),
            }
        )
    research = aggregate.research_feedback
    return {
        "artifact_dir": str(Path(artifact_dir).expanduser().resolve()),
        "windows": windows,
        "research": (
            {
                "hints": [hint.to_dict() for hint in research.hints],
                "asr_corrections": list(research.asr_corrections),
                "uncertainties": list(research.uncertainties),
                "warnings": list(research.warnings),
                "retrieval_urls": list(research.retrieval_urls),
            }
            if research is not None
            else None
        ),
        "merged_hints": [hint.to_dict() for hint in aggregate.all_hints()],
        "asr_corrections": aggregate.merged_asr_corrections(),
        "uncertainties": aggregate.merged_uncertainties(),
        "warnings": list(aggregate.warnings),
    }


def _refined_update(payload: Mapping[str, Any]) -> dict[str, Any]:
    from finesub.llm.knowledge.update import derive_task_paths, run_knowledge_update

    values = [str(value) for value in payload.get("llm_model") or []]
    artifact_dir = derive_task_paths(str(payload["final_srt"]))["artifact_dir"]
    with _routing_override(values):
        report = run_knowledge_update(
            final_srt=str(payload["final_srt"]),
            artifact_dir=artifact_dir,
            refined_srt=str(payload["refined_srt"]),
            task_id=str(payload["task_id"]),
            task_summary=str(payload.get("task_summary") or ""),
            knowledge_root=_root(),
            execute=True,
            apply=bool(payload.get("apply", True)),
            resume=bool(payload.get("resume", True)),
        )
    return _json_safe(report)


def _dispatch(payload: Mapping[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "")
    if action == "snapshot":
        return _snapshot()
    if action == "entry":
        rev = payload.get("rev")
        return _entry(
            str(payload.get("name") or ""),
            int(rev) if rev is not None else None,
        )
    if action in {"maintenance", "share"}:
        args = payload.get("args") or []
        if not isinstance(args, list):
            raise ValueError("command args must be a list")
        return _run_cli(
            action,
            str(payload.get("command") or ""),
            [str(value) for value in args],
            str(payload.get("content") or ""),
        )
    if action == "feedback":
        return _feedback(str(payload.get("final_srt") or ""))
    if action == "refined_update":
        return _refined_update(payload)
    raise ValueError(f"unsupported knowledge action: {action}")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.readline())
        if not isinstance(payload, dict):
            raise ValueError("knowledge worker request must be a JSON object")
        stdout = StringIO()
        stderr = StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            data = _dispatch(payload)
        logs = "\n".join(
            part.strip() for part in (stdout.getvalue(), stderr.getvalue()) if part.strip()
        )
        if logs and "output" not in data:
            data = {**data, "output": logs}
        envelope = {"ok": True, "data": _json_safe(data)}
        exit_code = 0
    except Exception as error:
        envelope = {
            "ok": False,
            "error": {
                "message": str(error) or type(error).__name__,
                "detail": traceback.format_exc(),
            },
        }
        exit_code = 1
    print(json.dumps(envelope, ensure_ascii=False, default=str, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
