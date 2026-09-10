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
from desktop.backend.worker.main import _publish_output, _routing_override
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
) -> list[BatchItemSnapshot]:
    from finesub.pipeline import OutputClaims, build_item
    from finesub.scheduler import run_batch
    from finesub.stages import default_pipeline_paths

    batch_root.mkdir(parents=True, exist_ok=True)
    workers = request.workers.model_dump(mode="python")
    claims = OutputClaims()
    items = []
    llm_model = request.items[0].llm_model
    with _routing_override(llm_model):
        for index, row in enumerate(request.items):
            try:
                items.append(
                    build_item(
                        _item_options(
                            row, workers, task_id=f"{batch_id}-{index + 1}"
                        ),
                        claims=claims,
                    )
                )
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
            rows.append(
                BatchItemSnapshot(
                    index=index,
                    input=request.items[index].input,
                    label=items[index].label,
                    state=state,
                    stage=result.stage,
                    error=error,
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

    with _routing_override(llm_model):
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
    request_line = sys.stdin.readline()
    if not request_line:
        raise ValueError("batch request is missing")
    request = BatchRequest.model_validate_json(request_line)
    batch_root = Path(
        os.environ.get("FINESUB_DESKTOP_BATCH_ROOT", "")
    ).expanduser()
    if not str(batch_root) or str(batch_root) == ".":
        raise RuntimeError("FINESUB_DESKTOP_BATCH_ROOT is required")
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
