from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from desktop.backend.jobs.launch import WorkerLaunchContext


class KnowledgeOperationError(RuntimeError):
    """A structured failure returned by the isolated knowledge worker."""

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


class KnowledgeService:
    """Run core knowledge operations in the managed FineSub environment.

    The desktop launcher intentionally does not import the full LLM/knowledge
    stack. One short-lived worker keeps the packaged executable small, uses
    exactly the same pinned core as a subtitle task, and isolates CLI routing
    state and SQLite connections from the long-running GUI process.
    """

    def __init__(
        self,
        knowledge_root: str | Path,
        context_provider: Callable[[], WorkerLaunchContext],
        *,
        process_runner: Callable[..., Any] = subprocess.run,
        timeout_seconds: int = 3600,
    ) -> None:
        self.root = Path(knowledge_root).expanduser().resolve()
        self.context_provider = context_provider
        self.process_runner = process_runner
        self.timeout_seconds = timeout_seconds

    def snapshot(self) -> dict[str, Any]:
        return self._invoke({"action": "snapshot"})

    def entry(self, name: str, rev: int | None = None) -> dict[str, Any]:
        return self._invoke({"action": "entry", "name": name, "rev": rev})

    def maintenance(
        self,
        command: str,
        args: list[str],
        *,
        content: str = "",
    ) -> dict[str, Any]:
        return self._invoke(
            {
                "action": "maintenance",
                "command": command,
                "args": args,
                "content": content,
            }
        )

    def share(self, command: str, args: list[str]) -> dict[str, Any]:
        return self._invoke(
            {"action": "share", "command": command, "args": args}
        )

    def feedback(self, final_srt: str | Path) -> dict[str, Any]:
        return self._invoke({"action": "feedback", "final_srt": str(final_srt)})

    def refined_update(
        self,
        *,
        final_srt: str | Path,
        refined_srt: str | Path,
        task_id: str,
        task_summary: str,
        llm_model: list[str],
        apply: bool,
        resume: bool,
    ) -> dict[str, Any]:
        return self._invoke(
            {
                "action": "refined_update",
                "final_srt": str(final_srt),
                "refined_srt": str(refined_srt),
                "task_id": task_id,
                "task_summary": task_summary,
                "llm_model": llm_model,
                "apply": apply,
                "resume": resume,
            }
        )

    def _invoke(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        context = self.context_provider()
        environment = os.environ.copy()
        environment.update(context.environment)
        environment["FINESUB_KNOWLEDGE_ROOT"] = str(self.root)
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        )
        result = self.process_runner(
            [
                context.python_executable,
                "-m",
                "desktop.backend.worker.knowledge_main",
            ],
            input=json.dumps(payload, ensure_ascii=False) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=context.working_directory,
            env=environment,
            creationflags=creationflags,
            timeout=self.timeout_seconds,
            check=False,
        )
        envelope = self._decode_envelope(result.stdout)
        if envelope is None:
            detail = (result.stderr or result.stdout or "").strip()
            raise KnowledgeOperationError(
                "知识库运行组件没有返回有效结果。",
                detail=detail,
            )
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            raise KnowledgeOperationError(
                str(error.get("message") or "知识库操作失败。"),
                detail=str(error.get("detail") or result.stderr or ""),
            )
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise KnowledgeOperationError("知识库运行组件返回了无效数据。")
        return data

    @staticmethod
    def _decode_envelope(output: str) -> dict[str, Any] | None:
        for line in reversed(output.splitlines()):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "ok" in value:
                return value
        return None
