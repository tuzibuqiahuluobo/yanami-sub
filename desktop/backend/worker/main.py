from __future__ import annotations

import argparse
from collections.abc import Callable
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from typing import Any, Protocol

from finesub.reporting import quieted_libraries, reporting_to
from finesub.speech.runtime.resources import check_tier_device_agreement
from finesub_bootstrap.artifacts import (
    DELIVERABLE_KEY_BY_STAGE,
    DELIVERABLE_SUFFIX_BY_STAGE,
    cleanup_intermediate,
)
from finesub_bootstrap.locks import (
    LockUnavailable,
    TASK_ACTIVITY_ROOT_VARIABLE,
    active_lock_path,
    holding_activity,
    holding_lock,
    lease_record,
    task_lock_path,
    task_workspace_lock_path,
)

from desktop.backend.common.models import TaskRequest
from desktop.backend.settings.local_agents import install_local_agent_command_overrides
from desktop.backend.worker.agent_health_check import (
    check_agent_health,
    validate_source_availability,
)
from desktop.backend.worker.model_source import source_route
from desktop.backend.worker.protocol import EventLogWriter, WorkerEvent, encode_event


class PipelineCallable(Protocol):
    def __call__(self, source: str, **kwargs: Any) -> Any: ...


Emit = Callable[[WorkerEvent], None]


class WorkerReporter:
    """Turn pipeline events into the protocol the launcher already speaks.

    Stage transitions become `stage` events, which is what the progress list
    renders. Everything else -- summaries, warnings, the final path -- becomes
    a log line, because that is the channel the drawer and `task-log.txt`
    share. `debug` becomes a `debug` event, which reaches the file only:
    diagnosing a desktop run should not mean reproducing it on the CLI, but
    per-group recovery detail would spend the whole drawer budget.
    """

    def __init__(self, task_id: str, emit: Emit) -> None:
        self.task_id = task_id
        self.emit = emit

    def planned(self, stages) -> None:
        return

    def stage_started(self, stage: str, *, reused: bool = False, detail: str = "") -> None:
        # The pipeline names the stage it is entering. Announcing anything
        # before that -- the requested stage, in particular -- is a claim about
        # where the run is that nothing has established: it read as every
        # earlier stage being finished the moment the task started.
        self.emit(
            WorkerEvent.progress(
                self.task_id,
                stage=stage,
                message="已有结果，跳过" if reused else (detail or "正在处理"),
                reused=reused,
            )
        )

    def progress(self, stage, *, completed, total=None, unit="", detail="") -> None:
        # Deliberately not a log line per update: the UI shows the stage, and
        # the counts would be hundreds of rows in the task log.
        return

    def summary(self, stage: str, metrics) -> None:
        body = "，".join(
            f"{label} {value}"
            for label, value in metrics.items()
            if value not in (None, 0, "")
        )
        if body:
            self._log(f"{stage}: {body}")

    def warning(self, code: str, message: str, *, impact: str = "", action: str = "") -> None:
        tail = "；".join(part for part in (impact, action) if part)
        self._log(f"Warning: {message}" + (f"（{tail}）" if tail else ""))

    def debug(self, message: str, fields=None) -> None:
        body = " ".join(f"{key}={value}" for key, value in (fields or {}).items())
        self.emit(
            WorkerEvent.debug(self.task_id, f"{message} {body}".strip())
        )

    def completed(self, output, elapsed_sec: float) -> None:
        self._log(f"完成：{output}")

    def failed(self, stage: str, message: str) -> None:
        self._log(f"失败（{stage}）：{message}")

    def _log(self, message: str) -> None:
        self.emit(WorkerEvent.log(self.task_id, message))


# Which `PipelinePaths` attribute holds each stage's subtitle. The name it is
# recorded under, and the file it resolves to, are `finesub_bootstrap.artifacts`
# -- shared with the CLI so both front ends file a subtitle the same way.
_PATHS_ATTRIBUTE_BY_STAGE = {
    "raw-srt": "raw_srt",
    "translated-srt": "translated_srt",
    "final-srt": "final_srt",
}

# These are expert results, not shared deliverables: keep them in the private
# task workspace and use desktop-only keys so old CLI/history readers continue
# to see exactly the three subtitle keys they understand.
_EXPERT_OUTPUT_BY_STAGE = {
    "vocal": ("vocalAudio", "vocal_audio"),
    "aligned": ("alignedJson", "aligned_json"),
    "stable": ("stableJson", "stable_json"),
}


def _claimed_outputs() -> set[Path]:
    """Every subtitle path this machine's task index already claims as ours.

    Publishing beside the user's own media means the name we want may already
    be taken. A path we wrote before is ours to replace -- rerunning a file has
    to land on the same name, or one video accumulates a folder of copies. A
    path we have never written belongs to whoever put it there.

    The index is read directly rather than taken from the request: `TaskRequest`
    is the front end's payload and is persisted verbatim, so a field saying
    "this file is ours" would let a front end claim any path on the disk.

    A machine whose index cannot be read yields nothing, which errs towards
    writing a new name rather than overwriting a stranger's subtitle.

    RC6.13+: Returns dict mapping Path to (size, mtime) tuple for verification.
    """

    from finesub.paths import resolve_managed_app_paths
    from finesub_bootstrap import task_index

    # The worker is handed a task id and a request, never a layout, so it
    # resolves the installation the same way any other process without an
    # environment does: the package shipping this code, else the managed
    # location every front end shares.
    app_paths = resolve_managed_app_paths()
    if app_paths is None:
        return {}
    claimed: dict[Path, tuple[int, float]] = {}
    for entry in task_index.read(
        app_paths.user_data / "tasks.json", app_paths.tasks
    ):
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict):
            continue
        metadata = entry.get("output_metadata", {})
        for key, value in outputs.items():
            if isinstance(value, str) and value:
                path = Path(value).expanduser().resolve()
                # Store size and mtime for verification
                meta = metadata.get(key, {}) if isinstance(metadata, dict) else {}
                size = meta.get("size", 0) if isinstance(meta, dict) else 0
                mtime = meta.get("mtime", 0.0) if isinstance(meta, dict) else 0.0
                claimed[path] = (size, mtime)
    return claimed


def _file_unchanged(path: Path, expected_size: int, expected_mtime: float) -> bool:
    """Check if file matches expected size and mtime (not user-modified)."""
    try:
        stat = path.stat()
        # Allow small mtime drift (filesystem precision varies)
        return stat.st_size == expected_size and abs(stat.st_mtime - expected_mtime) < 2.0
    except OSError:
        return False


def _unclaimed_destination(destination: Path) -> Path:
    """`destination`, or a free name beside it when a stranger holds that one.

    RC6.13+: If destination exists and is claimed but has been modified by the
    user (different size or mtime), treat it as unclaimed to avoid data loss.
    """

    if not destination.exists():
        return destination
    claimed = _claimed_outputs()
    if destination in claimed:
        size, mtime = claimed[destination]
        # Only reuse if file is unchanged since we wrote it
        if _file_unchanged(destination, size, mtime):
            return destination
        # File was modified by user - don't overwrite
    candidate = destination.with_name(
        f"{destination.stem}.finesub{destination.suffix}"
    )
    serial = 2
    while candidate.exists():
        # Check if this candidate is also claimed and unchanged
        if candidate in claimed:
            size, mtime = claimed[candidate]
            if _file_unchanged(candidate, size, mtime):
                return candidate
        candidate = destination.with_name(
            f"{destination.stem}.finesub.{serial}{destination.suffix}"
        )
        serial += 1
    return candidate


def _publish_output(
    paths: Any,
    request: TaskRequest,
    *,
    task_id: str,
) -> dict[str, str]:
    """Expose the requested result; publish only subtitles beside local media."""

    expert = _EXPERT_OUTPUT_BY_STAGE.get(request.stage)
    if expert is not None:
        key, attribute = expert
        generated = Path(getattr(paths, attribute)).expanduser().resolve()
        if not generated.is_file():
            raise FileNotFoundError(
                f"FineSub completed without producing {request.stage}: {generated}"
            )
        return {key: str(generated)}

    attribute = _PATHS_ATTRIBUTE_BY_STAGE.get(request.stage)
    key = DELIVERABLE_KEY_BY_STAGE.get(request.stage)
    suffix = DELIVERABLE_SUFFIX_BY_STAGE.get(request.stage)
    # All three, because they are separate tables: a stage added to one and not
    # the others should publish nothing, the way an unknown stage always has,
    # rather than raise inside the worker and fail an otherwise finished task.
    if attribute is None or key is None or suffix is None:
        return {}
    generated = Path(getattr(paths, attribute)).expanduser().resolve()
    if not generated.is_file():
        raise FileNotFoundError(
            f"FineSub completed without producing {request.stage}: {generated}"
        )

    imported = Path(request.input).expanduser()
    if not imported.is_file():
        return {key: str(generated)}

    destination = _unclaimed_destination(
        imported.resolve().with_name(f"{imported.stem}{suffix}")
    )
    if destination != generated:
        temporary = destination.with_name(
            f".{destination.name}.{task_id}.part"
        )
        temporary.unlink(missing_ok=True)
        try:
            shutil.copy2(generated, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    return {key: str(destination)}


def _resolve_output_path(request: TaskRequest) -> str | None:
    """Map the request's naming choice onto the pipeline's output path.

    ``output`` is an explicit path and wins. ``name`` is the CLI's ``--name``:
    a bare stem that produces out/<name>/<name>.srt, leaving the location alone.
    """

    if request.output:
        return request.output
    if not request.name:
        return None
    from finesub.paths import resolve_name_output_path

    return str(resolve_name_output_path(request.name))


@contextmanager
def _routing_override(values: list[str]):
    """Apply one task's core route pin without leaking it across tests/calls."""

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


def _execute_pipeline(
    request: TaskRequest,
    *,
    stage: str,
    task_id: str,
    pipeline: PipelineCallable,
    knowledge: str | None = None,
) -> Any:
    return pipeline(
        request.input,
        output_path=_resolve_output_path(request),
        stage=stage,
        model_name=request.model_name,
        device=request.device,
        language=request.language,
        gpu_tier=request.gpu_tier,
        gap_sec=request.gap_sec,
        separator_sample_rate=request.separator_sample_rate,
        separate=request.separate,
        vad_silero_assist=request.vad_silero_assist,
        qwen_verify=request.qwen_verify,
        lang_redecode=request.lang_redecode,
        asr_decode_batch=request.asr_decode_batch,
        asr_context=request.asr_context,
        word=request.word,
        asr_stabilize_profile=request.asr_stabilize_profile,
        split_length_scale=request.split_length_scale,
        llm_media=request.llm_media,
        llm_correction_media=request.llm_correction_media,
        llm_planning_media=request.llm_planning_media,
        llm_retrieval=request.llm_retrieval,
        llm_difficulty=request.llm_difficulty,
        llm_continuity=request.llm_continuity,
        llm_parallel_windows=request.llm_parallel_windows,
        llm_fast=request.llm_fast,
        llm_output_scale=request.llm_output_scale,
        llm_video=request.llm_video,
        extra_info=request.extra_info,
        extra_style=request.extra_style,
        task_summary=request.task_summary,
        style=request.style,
        style_mode=request.style_mode,
        download_video_source=request.download_video_source,
        knowledge=request.knowledge if knowledge is None else knowledge,
        refined_srt=request.refined_srt,
        task_id=task_id,
        postprocess_profile=request.postprocess_profile,
        max_retries_per_window=request.max_retries_per_window,
        max_replacements_per_window=request.max_replacements_per_window,
        resume=request.resume,
    )


def _expected_subtitles(request: TaskRequest) -> tuple[Path, Path] | None:
    # The desktop and batch managers resolve an explicit output before
    # launching the worker. Without it, a URL can resolve to a different video
    # id; guessing an output path could mislabel a completed correction.
    output = _resolve_output_path(request)
    if not output:
        return None
    final = Path(output).expanduser()
    if not final.suffix:
        final = final.with_suffix(".srt")
    translated = final.with_name(f"{final.stem}-translated.srt")
    return translated, final


def _raw_subtitle_available(request: TaskRequest) -> bool:
    """True once the pipeline's pre-correction transcript exists on disk.

    Source-agnostic proof that upstream stages (separation/ASR/stabilize)
    already succeeded, usable as evidence for API-sourced failures which
    carry none of the Agent-harness-specific error attributes below.
    """

    outputs = _expected_subtitles(request)
    if outputs is None:
        return False
    _translated, final = outputs
    raw = final.with_name(f"{final.stem}-raw.srt")
    return raw.is_file()


def _correction_exhausted(request: TaskRequest, error: Exception, *, source: str) -> bool:
    """True when only the correction/translation stage failed, for either
    model source, and it is safe to fall back to the raw subtitle.

    RC6.13+: API errors are now checked for permanent failure kinds (invalid
    API key, authentication errors) just like Agent errors, so configuration
    mistakes aren't silently masked as "correction skipped, raw subtitle
    preserved".

    Renamed from `_agent_correction_exhausted`. The previous version only
    recognized Agent-harness-specific error markers (`CapabilityUnavailableError`,
    `_harness_route_decision`), so it never matched an API-sourced failure --
    those always propagated as a hard task failure, contradicting the
    "保留原始字幕" behavior RC6.10 documents.
    """

    outputs = _expected_subtitles(request)
    if outputs is None:
        return False
    translated, final = outputs
    if translated.is_file() or final.is_file():
        return False  # never mask a failure once real output already exists

    matched = type(error).__name__ == "CapabilityUnavailableError"
    if not matched:
        decision = getattr(error, "_harness_route_decision", None)
        if isinstance(decision, dict):
            candidates = decision.get("candidates")
            rows = [item for item in candidates if isinstance(item, dict)] if isinstance(candidates, list) else []
            matched = bool(rows) and len(rows) == len(candidates) and all(
                item.get("reason") not in {"fallback_not_allowed", "permanent_failure"}
                and item.get("failure_kind") != "permanent"
                and item.get("decision") != "pending"
                and item.get("outcome") != "success"
                for item in rows
            )

    # RC6.13+: For API source, check for permanent failures instead of
    # blindly accepting any error. Common permanent failures include:
    # - Invalid API key (authentication errors)
    # - API key without required permissions
    # - Malformed requests (should not happen, but if they do, should fail loudly)
    if not matched and source == "api":
        # Check if this looks like a permanent configuration error
        error_str = str(error).lower()
        error_type = type(error).__name__

        # Permanent failure indicators (should NOT be masked)
        permanent_indicators = [
            "invalid api key",
            "invalid_api_key",
            "authentication",
            "unauthorized",
            "forbidden",
            "permission denied",
            "api key not found",
            "invalid key",
        ]

        if any(indicator in error_str for indicator in permanent_indicators):
            # This is a configuration error - fail loudly, don't mask it
            return False

        # Check harness failure_kind if available (works for both API and Agent)
        failure_kind = getattr(error, "failure_kind", None)
        if failure_kind == "permanent":
            return False

        # For other API errors (transient failures, rate limits, etc.),
        # allow fallback to raw subtitle
        matched = True

    if not matched:
        return False
    # Batch processing already required this before publishing a raw
    # fallback; single-task execution did not. Applying it everywhere closes
    # that gap: never claim "raw subtitle preserved" when there is in fact
    # no raw file on disk to preserve.
    return _raw_subtitle_available(request)


# Backward-compat alias: keep the old name importable (batch_main.py and any
# external tooling may still reference it) while call sites move to the
# source-agnostic `_correction_exhausted`.
def _agent_correction_exhausted(request: TaskRequest, error: Exception) -> bool:
    return _correction_exhausted(request, error, source="agent")


def _failed_post_correction_knowledge_update(request: TaskRequest, error: Exception) -> bool:
    """Only recover a failed optional *post* update after subtitles exist."""

    if request.knowledge != "update" or request.stage not in {"translated-srt", "final-srt"}:
        return False
    outputs = _expected_subtitles(request)
    if outputs is None:
        return False
    translated, final = outputs
    generated = final if request.stage == "final-srt" else translated
    if not generated.is_file():
        return False
    tb = error.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_name == "_maybe_knowledge_update":
            return True
        tb = tb.tb_next
    return False


def _agent_error_detail(error: Exception) -> str:
    """Expose a bounded CLI stderr clue without copying whole capsules to UI."""

    attempts = getattr(error, "_harness_execution_attempts", None)
    if not isinstance(attempts, list):
        return ""
    for attempt in reversed(attempts):
        if isinstance(attempt, dict):
            vendor_error = str(attempt.get("vendor_error") or "").strip()
            if vendor_error:
                return vendor_error[:400]
        locator = attempt.get("evidence_locator") if isinstance(attempt, dict) else None
        if not isinstance(locator, dict):
            continue
        try:
            from finesub.llm.agent.agent_paths import resolve_evidence_locator

            stderr = resolve_evidence_locator(locator) / "events" / "stderr.log"
            if not stderr.is_file():
                continue
            with stderr.open("rb") as stream:
                stream.seek(max(0, stderr.stat().st_size - 4096))
                lines = stream.read().decode("utf-8", errors="replace").splitlines()
            detail = next((line.strip() for line in reversed(lines) if line.strip()), "")
            if detail:
                return detail[:400]
        except (OSError, ValueError):
            continue
    return ""


def _agent_error_message(error: Exception) -> str:
    message = str(error)
    detail = _agent_error_detail(error)
    return f"{message}；Agent 错误详情：{detail}" if detail else message


def _route_artifact_log(request: TaskRequest) -> tuple[Path | None, int]:
    outputs = _expected_subtitles(request)
    if outputs is None:
        return None, 0
    final = outputs[1]
    base = final.with_suffix("")
    path = base.with_name(f"{base.name}.llm-artifacts") / "task-artifacts.jsonl"
    try:
        return path, path.stat().st_size
    except OSError:
        return path, 0


def _agent_route_failures(
    decision: object, attempts: object, log: Callable[[str], None], seen: set[str]
) -> None:
    if not isinstance(decision, dict):
        return
    candidates = decision.get("candidates")
    if not isinstance(candidates, list):
        return
    attempt_rows = [row for row in attempts if isinstance(row, dict)] if isinstance(attempts, list) else []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        failed = candidate.get("outcome") == "failed"
        unavailable = candidate.get("decision") == "skipped" and candidate.get("reason") in {
            "backend_unavailable", "provider_disabled", "capability_mismatch"
        }
        if not (failed or unavailable):
            continue
        target = str(candidate.get("target_id") or "").strip()
        if not target:
            continue
        reason = str(candidate.get("failure_kind") or candidate.get("reason") or "unknown")
        detail = next(
            (str(row.get("vendor_error") or "").strip() for row in reversed(attempt_rows)
             if row.get("target_id") == target and row.get("vendor_error")),
            str(candidate.get("detail") or "").strip(),
        )[:400]

        # Build a user-friendly message with actionable guidance
        message = f"本地 Agent {target} 未能使用（{reason}）"
        if detail:
            message += f"：{detail}"

        # Add actionable guidance based on reason
        if reason == "quota":
            message += "\n  → 建议：请充值 API 配额后重试"
        elif reason == "provider_disabled":
            message += "\n  → 建议：请在设置中检查该 Agent 是否被禁用，或重新运行健康检查"
        elif reason == "transient":
            message += "\n  → 建议：临时错误，可能是网络问题或服务暂时不可用，请稍后重试"
        elif reason == "backend_unavailable":
            message += "\n  → 建议：Agent 后端不可用，请检查 Agent 是否正确安装和配置"
        elif reason == "capability_mismatch":
            message += "\n  → 建议：Agent 不支持当前任务所需的能力（如音频处理），请选择其他 Agent 或调整任务设置"

        if message not in seen and len(seen) < 24:
            seen.add(message)
            log(message)


def _artifact_agent_route_failures(
    path: Path | None, offset: int, log: Callable[[str], None], seen: set[str]
) -> None:
    if path is None:
        return
    try:
        with path.open("rb") as stream:
            stream.seek(offset if path.stat().st_size >= offset else 0)
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                payload = row.get("payload") if isinstance(row, dict) else None
                if isinstance(payload, dict):
                    _agent_route_failures(
                        payload.get("route_decision"), payload.get("execution_attempts"), log, seen
                    )
    except OSError:
        return


def run_request(
    request: TaskRequest,
    *,
    task_id: str,
    pipeline: PipelineCallable,
    emit: Emit,
) -> dict[str, str]:
    emit(WorkerEvent.started(task_id))

    # Pre-check: validate model source availability before expensive ASR stages
    if request.stage in {"translated-srt", "final-srt"} and request.llm_source != "manual":
        emit(WorkerEvent.log(task_id, "正在检查模型源可用性..."))

        # Perform agent health check for agent/auto modes
        should_check_agents = request.llm_source in {"agent", "auto"}
        is_available, error_message = validate_source_availability(
            request.llm_source,
            check_agents=should_check_agents,
        )

        if not is_available:
            emit(WorkerEvent.log(task_id, f"模型源检查失败：{error_message}"))
            emit(WorkerEvent.failed(task_id, error_message))
            raise ValueError(error_message)

        # Log detailed health report for agent mode
        if should_check_agents:
            report = check_agent_health()
            if report.statuses:
                summary = report.format_summary()
                emit(WorkerEvent.log(task_id, f"Agent 健康检查：{summary}"))

                # Log detailed status for each unavailable agent
                for status in report.statuses:
                    if not status.available:
                        detail_msg = f"Agent {status.tier} 不可用"
                        if status.reason:
                            detail_msg += f"（{status.reason}）"
                        if status.detail:
                            detail_msg += f"：{status.detail}"
                        emit(WorkerEvent.log(task_id, detail_msg))

                # If no agents available at all, fail early
                if not report.any_available:
                    error_msg = (
                        "所有配置的本地 Agent 均不可用。"
                        "请在设置中检查 Agent 配置，或选择使用 API 模式。"
                    )
                    emit(WorkerEvent.log(task_id, error_msg))
                    emit(WorkerEvent.failed(task_id, error_msg))
                    raise ValueError(error_msg)

    try:
        # "normal": the drawer and the task log get the pipeline's own report,
        # not a library's version banner or a progress bar flattened into a
        # file. Verbose detail still reaches the file, as debug events.
        with (
            source_route(request) as route,
            _routing_override(route.models),
            reporting_to(WorkerReporter(task_id, emit)),
            quieted_libraries("normal"),
        ):
            # Same refusal the CLI gives, so the two front ends answer one
            # input the same way. Reachable only because `device` can be None:
            # with a default of "cuda" this could not tell a choice from a
            # default and would have rejected a bare `cpu` tier.
            check_tier_device_agreement(request.gpu_tier, request.device)
            if route.targets:
                emit(WorkerEvent.log(task_id, f"模型来源：{route.source}；尝试顺序：{', '.join(route.targets)}"))
            artifact_log, artifact_offset = _route_artifact_log(request)
            logged_agent_failures: set[str] = set()
            effective_stage = "raw-srt" if route.skip_reason else request.stage
            skip_reason = route.skip_reason
            try:
                paths = _execute_pipeline(request, stage=effective_stage, task_id=task_id, pipeline=pipeline)
            except Exception as error:
                if route.source == "agent":
                    _agent_route_failures(
                        getattr(error, "_harness_route_decision", None),
                        getattr(error, "_harness_execution_attempts", None),
                        lambda message: emit(WorkerEvent.log(task_id, message)),
                        logged_agent_failures,
                    )
                if _failed_post_correction_knowledge_update(request, error):
                    emit(WorkerEvent.log(
                        task_id,
                        "字幕已生成，但后置知识库更新失败；保留字幕并跳过本次知识库更新："
                        + _agent_error_message(error),
                    ))
                    paths = _execute_pipeline(
                        request, stage=effective_stage, task_id=task_id,
                        pipeline=pipeline, knowledge="none",
                    )
                elif _correction_exhausted(request, error, source=route.source):
                    skip_reason = (
                        f"所有本地 Agent 均未完成纠错翻译：{_agent_error_message(error)}"
                        if route.source == "agent" else
                        f"纠错翻译失败，已保留原始字幕：{_agent_error_message(error)}"
                    )
                    emit(WorkerEvent.log(task_id, skip_reason))
                    effective_stage = "raw-srt"
                    paths = _execute_pipeline(request, stage=effective_stage, task_id=task_id, pipeline=pipeline)
                else:
                    raise
            if route.source == "agent":
                _artifact_agent_route_failures(
                    artifact_log, artifact_offset,
                    lambda message: emit(WorkerEvent.log(task_id, message)),
                    logged_agent_failures,
                )
            effective_request = request.model_copy(update={"stage": effective_stage})
            outputs = _publish_output(paths, effective_request, task_id=task_id)
            if skip_reason:
                emit(WorkerEvent.log(task_id, skip_reason))
                emit(WorkerEvent.progress(task_id, stage="translated-srt", message=skip_reason, skipped=True))
        if request.cleanup_intermediate and outputs:
            # `outputs` is empty for the stages that produce no subtitle
            # (`vocal`/`aligned`/`stable`), and with nothing to preserve the
            # cleanup deleted the very artifact the task was asked for: a green
            # task, an empty `outputs`, and nothing to open. The desktop UI only
            # offers the subtitle stages today, so this was a bridge-contract
            # hole rather than a visible one -- but `TaskRequest` accepts all of
            # them and `validate_stage` only guards the two LLM stages.
            cleanup_intermediate(
                paths.final_srt,
                preserve=outputs.values(),
            )
    except Exception as error:
        emit(WorkerEvent.failed(task_id, _agent_error_message(error)))
        raise
    emit(WorkerEvent.completed(task_id, outputs))
    return outputs


@contextmanager
def _announcing_this_task(task_id: str, output: str | None = None):
    """Own this task id and announce writes for as long as we run.

    The launcher used to hold this, which said nothing in the one case it
    exists for: closing the window does not stop us -- we are our own process
    group -- so the lock was released while this process kept writing, and
    `finesub relocate` and the task-outputs migration were free to move the
    tree out from under it. Held here it stays true even when we are orphaned,
    and the OS drops it when we actually end.

    The per-task lock is mandatory: without it, retrying from two front ends
    can corrupt the same artifacts. The tree-wide announcement remains best
    effort because unrelated tasks are allowed to run concurrently. Only
    taking that advisory lock is guarded; errors from the run itself must
    propagate unchanged.
    """

    tasks_root = os.environ.get("FINESUB_TASKS_ROOT", "")
    activity_root = os.environ.get(TASK_ACTIVITY_ROOT_VARIABLE, "")
    if not tasks_root:
        yield None
        return
    if not activity_root:
        raise RuntimeError(
            f"{TASK_ACTIVITY_ROOT_VARIABLE} is required for a managed task"
        )
    with ExitStack() as stack:
        stack.enter_context(holding_activity(Path(activity_root)))
        root = Path(tasks_root)
        root.mkdir(parents=True, exist_ok=True)
        stack.enter_context(
            holding_lock(
                task_lock_path(root, task_id),
                timeout=5,
                lease=lease_record(task_id, "desktop"),
            )
        )
        if output:
            # Fixed order across CLI and workers: identity before workspace.
            # Two task ids may intentionally reuse one output directory.
            stack.enter_context(
                holding_lock(
                    task_workspace_lock_path(root, output), timeout=5
                )
            )
        try:
            stack.enter_context(holding_lock(active_lock_path(root), timeout=5))
        except (OSError, LockUnavailable):
            pass
        yield None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FineSub isolated desktop worker")
    parser.add_argument("--task-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    install_local_agent_command_overrides()
    request_line = sys.stdin.readline()
    if not request_line:
        raise ValueError("worker request is missing")
    request = TaskRequest.model_validate(json.loads(request_line))

    protocol_output = sys.stdout

    def emit(event: WorkerEvent) -> None:
        protocol_output.write(encode_event(event))
        protocol_output.flush()

    log_writer = EventLogWriter(args.task_id, emit)
    try:
        with _announcing_this_task(args.task_id, request.output), redirect_stdout(
            log_writer
        ), redirect_stderr(log_writer):
            from finesub.stages import run_pipeline

            run_request(
                request,
                task_id=args.task_id,
                pipeline=run_pipeline,
                emit=emit,
            )
        return 0
    except Exception as error:
        traceback.print_exc(file=log_writer)
        log_writer.flush()
        emit(
            WorkerEvent.failed(
                args.task_id,
                f"{type(error).__name__}: {error}",
            )
        )
        return 1
    finally:
        log_writer.flush()


if __name__ == "__main__":
    raise SystemExit(main())
