from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from desktop.backend.worker.protocol import decode_worker_stream_text


BatchEventType = Literal["started", "snapshot", "log", "completed", "failed"]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class BatchWorkerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: BatchEventType
    batch_id: str
    timestamp: str = Field(default_factory=_timestamp)
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def log(cls, batch_id: str, message: str) -> "BatchWorkerEvent":
        return cls(type="log", batch_id=batch_id, payload={"message": message})


def encode_batch_event(event: BatchWorkerEvent) -> str:
    return json.dumps(
        {
            "type": event.type,
            "batchId": event.batch_id,
            "timestamp": event.timestamp,
            "payload": event.payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"


def parse_batch_event(line: str, *, batch_id: str) -> BatchWorkerEvent:
    line = decode_worker_stream_text(line)
    try:
        body = json.loads(line)
        event = BatchWorkerEvent.model_validate(
            {
                "type": body["type"],
                "batch_id": body["batchId"],
                "timestamp": body["timestamp"],
                "payload": body.get("payload", {}),
            }
        )
        if event.batch_id != batch_id:
            raise ValueError("event belongs to another batch")
        return event
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return BatchWorkerEvent.log(batch_id, line.rstrip("\r\n"))
