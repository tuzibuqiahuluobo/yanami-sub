from __future__ import annotations

import argparse
from contextlib import nullcontext, redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import sys
import threading
import traceback
from typing import Any

from finesub.reporting import quieted_libraries
from finesub_bootstrap.artifacts import cleanup_intermediate
from finesub_bootstrap.locks import TASK_ACTIVITY_ROOT_VARIABLE, holding_activity

from desktop.backend.batches.protocol import BatchWorkerEvent, encode_batch_event
from desktop.backend.common.models import (
    BatchItemRequest,
    BatchItemSnapshot,
    BatchRequest,
)
from desktop.backend.settings.local_agents import install_local_agent_command_overrides
from desktop.backend.worker.main import (
    _agent_correction_exhausted,
    _agent_error_message,
    _agent_route_failures,
    _artifact_agent_route_failures,
    _expected_subtitles,
    _failed_post_correction_knowledge_update,
    _publish_output,
    _route_artifact_log,
    _routing_override,
)
from desktop.backend.worker.model_source import source_route
from desktop.backend.worker.protocol import EventLogWriter


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FineSub isolated desktop batch worker")
    parser.add_argument("--batch-id", required=True)
    return parser.parse_args()


def _item_options(
    item: BatchItemRequest, workers: dict[str, int], *, task_id: str
) -> dict[str, Any]:
    options = item.model_dump(mode="python")
    options["source"] = options.pop("input")
    options.pop("cleanup_intermediate", None)
    options.pop("llm_model", None)
    options.pop("llm_source", None)
    options["task_id"] = task_id
    options["_batch_workers"] = workers
    return options


def _failed_item(source: str, error: BaseException):
    from finesub.scheduler import BatchItem

    def fail(_payload: Any) -> Any:
        raise error

    return BatchItem(
        label=Path(source).name or source,
        stages={"download": fail},
        row={"source": source},
    )


def _read_published(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(body, dict):
        return {}
    return {
        str(key): {str(name): str(value) for name, value in outputs.items()}
        for key, outputs in body.items()
        if isinstance(outputs, dict)
    }


def run_batch_request(
    request: BatchRequest,
    *,
    batch_id: str,
    batch_root: Path,
    emit,
    build_item=None,
    run_batch=None,
    default_pipeline_paths=None,
    claims=None,
) -> list[BatchItemSnapshot]:
    if build_item is None or claims is None:
        from finesub.pipeline import OutputClaims, build_item as core_build_item

        build_item = build_item or core_build_item
        claims = claims or OutputClaims()
    if run_batch is None:
        from finesub.scheduler import run_batch as core_run_batch

        run_batch = core_run_batch
    if default_pipeline_paths is None:
        from finesub.stages import default_pipeline_paths as core_pipeline_paths

        default_pipeline_paths = core_pipeline_paths

    batch_root.mkdir(parents=True, exist_ok=True)
    workers = request.workers.model_dump(mode="python")
    items = []
    route_item = next(
        (item for item in request.items if item.stage in {"translated-srt", "final-srt"}),
        request.items[0],
    )
    skip_reasons: dict[int, str] = {}
    with source_route(route_item) as route, _routing_override(route.models):
        if route.targets:
            emit(BatchWorkerEvent.log(
                batch_id, f"模型来源：{route.source}；尝试顺序：{', '.join(route.targets)}"
            ))
        for index, row in enumerate(request.items):
            try:
                effective_row = row
                if route.skip_reason and row.stage in {"translated-srt", "final-srt"}:
                    skip_reasons[index] = route.skip_reason
                    effective_row = row.model_copy(update={"stage": "raw-srt"})
                item = build_item(
                    _item_options(
                        effective_row, workers, task_id=f"{batch_id}-{index + 1}"
                    ),
                    claims=claims,
                )
                if route.source == "agent" and not route.skip_reason and "llm" in item.stages:
                    original_llm = item.stages["llm"]

                    def guarded_llm(payload, *, _call=original_llm, _row=row, _index=index):
                        artifact_log, artifact_offset = _route_artifact_log(_row)
                        logged_failures: set[str] = set()

                        def log_failure(message: str) -> None:
                            emit(BatchWorkerEvent.log(batch_id, f"项目 {_index + 1}：{message}"))

                        try:
                            return _call(payload)
                        except Exception as error:
                            _agent_route_failures(
                                getattr(error, "_harness_route_decision", None),
                                getattr(error, "_harness_execution_attempts", None),
                                log_failure, logged_failures,
                            )
                            if _failed_post_correction_knowledge_update(_row, error):
                                emit(BatchWorkerEvent.log(
                                    batch_id,
                                    f"项目 {_index + 1} 字幕已生成，后置知识库更新失败并已跳过："
                                    f"{_agent_error_message(error)}",
                                ))
                                return payload
                            outputs = _expected_subtitles(_row)
                            if outputs and _agent_correction_exhausted(_row, error):
                                final = outputs[1]
                                raw = final.with_name(f"{final.stem}-raw.srt")
                                if raw.is_file():
                                    reason = (
                                        f"项目 {_index + 1} 所有本地 Agent 均未完成纠错翻译；"
                                        f"保留原始字幕：{_agent_error_message(error)}"
                                    )
                                    skip_reasons[_index] = reason
                                    emit(BatchWorkerEvent.log(batch_id, reason))
                                    return payload
                            raise
                        finally:
                            _artifact_agent_route_failures(
                                artifact_log, artifact_offset, log_failure, logged_failures
                            )

                    item.stages = {**item.stages, "llm": guarded_llm}
                items.append(item)
            except BaseException as error:  # one malformed/disappeared item may fail alone
                items.append(_failed_item(row.input, error))

    published_path = batch_root / "published.json"
    published = _read_published(published_path)
    publish_errors: dict[int, str] = {}
    publication_lock = threading.Lock()

    def save_published() -> None:
        temporary = published_path.with_name(f".{published_path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(published, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, published_path)

    def snapshots(results) -> list[BatchItemSnapshot]:
        rows: list[BatchItemSnapshot] = []
        for index, result in enumerate(results):
            state = result.view_state
            error = result.error
            if index in publish_errors:
                state = "failed"
                error = publish_errors[index]
            correction_skipped = bool(
                state == "done"
                and skip_reasons.get(index)
                and "rawSrt" in published.get(str(index), {})
            )
            rows.append(
                BatchItemSnapshot(
                    index=index,
                    input=request.items[index].input,
                    label=items[index].label,
                    state=state,
                    stage=result.stage,
                    error=error,
                    correction_skipped=correction_skipped,
                    skip_reason=skip_reasons[index] if correction_skipped else "",
                    outputs=published.get(str(index), {}),
                )
            )
        return rows

    def publish(_items, results) -> None:
        with publication_lock:
            for index, result in enumerate(results):
                key = str(index)
                existing = published.get(key, {})
                if result.status != "done":
                    continue
                if existing and all(Path(path).is_file() for path in existing.values()):
                    continue
                published.pop(key, None)
                item_request = request.items[index]
                if index in skip_reasons:
                    item_request = item_request.model_copy(update={"stage": "raw-srt"})
                try:
                    payload = result.payload or {}
                    paths = default_pipeline_paths(
                        payload["audio"], output_path=payload.get("output")
                    )
                    outputs = _publish_output(
                        paths,
                        item_request,
                        task_id=f"{batch_id}-{index + 1}",
                    )
                    published[key] = outputs
                    save_published()
                    if item_request.cleanup_intermediate and outputs:
                        cleanup_intermediate(
                            paths.final_srt,
                            preserve=outputs.values(),
                        )
                except Exception as error:  # publishing fails this item, not the batch
                    publish_errors[index] = f"{type(error).__name__}: {error}"
            emit(
                BatchWorkerEvent(
                    type="snapshot",
                    batch_id=batch_id,
                    payload={
                        "items": [row.model_dump(mode="json") for row in snapshots(results)]
                    },
                )
            )

    with source_route(route_item) as run_route, _routing_override(run_route.models):
        results = run_batch(
            items,
            workers=workers,
            asr_queue_size=request.asr_queue_size,
            retry_failed=request.retry_failed,
            status_path=batch_root / "batch-status.jsonl",
            publish=publish,
        )
    final = snapshots(results)
    emit(
        BatchWorkerEvent(
            type="completed",
            batch_id=batch_id,
            payload={"items": [row.model_dump(mode="json") for row in final]},
        )
    )
    return final


def main() -> int:
    args = _parse_args()
    install_local_agent_command_overrides()
    request_line = sys.stdin.readline()
    if not request_line:
        raise ValueError("batch request is missing")
    request = BatchRequest.model_validate_json(request_line)
    batch_root = Path(
        os.environ.get("YANAMI_SUB_BATCH_ROOT", "")
    ).expanduser()
    if not str(batch_root) or str(batch_root) == ".":
        raise RuntimeError("YANAMI_SUB_BATCH_ROOT is required")
    batch_root.mkdir(parents=True, exist_ok=True)

    protocol_output = sys.stdout
    write_lock = threading.Lock()

    def emit(event: BatchWorkerEvent) -> None:
        with write_lock:
            protocol_output.write(encode_batch_event(event))
            protocol_output.flush()

    def forward_log(event) -> None:
        emit(BatchWorkerEvent.log(args.batch_id, str(event.payload.get("message") or "")))

    log_writer = EventLogWriter(args.batch_id, forward_log)
    activity_root = os.environ.get(TASK_ACTIVITY_ROOT_VARIABLE, "")
    activity = (
        holding_activity(Path(activity_root)) if activity_root else nullcontext()
    )
    try:
        emit(BatchWorkerEvent(type="started", batch_id=args.batch_id))
        with activity, redirect_stdout(log_writer), redirect_stderr(log_writer), quieted_libraries(
            "normal"
        ):
            run_batch_request(
                request,
                batch_id=args.batch_id,
                batch_root=batch_root,
                emit=emit,
            )
        return 0
    except BaseException as error:
        traceback.print_exc(file=log_writer)
        log_writer.flush()
        emit(
            BatchWorkerEvent(
                type="failed",
                batch_id=args.batch_id,
                payload={"message": f"{type(error).__name__}: {error}"},
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
