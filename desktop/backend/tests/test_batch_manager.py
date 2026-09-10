from __future__ import annotations

from io import StringIO
from pathlib import Path
import time

import pytest

from desktop.backend.batches.manager import BatchManager
from desktop.backend.batches.protocol import (
    BatchWorkerEvent,
    encode_batch_event,
    parse_batch_event,
)
from desktop.backend.common.models import BatchRequest


class FakeProcess:
    def __init__(self, output: str, return_code: int = 0) -> None:
        self.stdin = StringIO()
        self.stdout = StringIO(output)
        self.return_code = return_code

    def poll(self):
        return self.return_code

    def wait(self):
        return self.return_code


def test_batch_protocol_turns_non_protocol_output_into_a_log() -> None:
    event = parse_batch_event("a library banner\n", batch_id="batch-1")

    assert event.type == "log"
    assert event.batch_id == "batch-1"
    assert event.payload["message"] == "a library banner"


def test_batch_manager_persists_core_worker_progress_and_owned_outputs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"media")
    published = tmp_path / "video-raw.srt"
    published.write_text("subtitle", encoding="utf-8")
    commands: list[list[str]] = []

    def process_factory(command, **_kwargs):
        commands.append(command)
        batch_id = command[-1]
        row = {
            "index": 0,
            "input": str(source),
            "label": source.name,
            "state": "done",
            "stage": "",
            "error": "",
            "outputs": {"rawSrt": str(published)},
        }
        output = "".join(
            [
                encode_batch_event(BatchWorkerEvent(type="started", batch_id=batch_id)),
                encode_batch_event(
                    BatchWorkerEvent(
                        type="snapshot", batch_id=batch_id, payload={"items": [row]}
                    )
                ),
                encode_batch_event(
                    BatchWorkerEvent(
                        type="completed", batch_id=batch_id, payload={"items": [row]}
                    )
                ),
            ]
        )
        return FakeProcess(output)

    manager = BatchManager(
        python_executable="python.exe",
        worker_env={},
        process_factory=process_factory,
        history_path=tmp_path / "user-data" / "batches.json",
        output_root=tmp_path / "tasks" / "batches",
    )
    started = manager.start(
        BatchRequest.model_validate({"items": [{"input": str(source)}]})
    )

    deadline = time.time() + 2
    current = manager.snapshot()
    while current is not None and current.state == "running" and time.time() < deadline:
        time.sleep(0.01)
        current = manager.snapshot()

    assert current is not None
    assert current.state == "completed"
    assert current.items[0].outputs == {"rawSrt": str(published)}
    assert Path(started.request.items[0].output or "").is_relative_to(
        tmp_path / "tasks" / "batches"
    )
    assert commands[0][2:4] == ["desktop.backend.worker.batch_main", "--batch-id"]
    assert (tmp_path / "user-data" / "batches.json").is_file()

    opened: list[Path] = []
    assert manager.open_owned_output(
        current.batch_id, str(published), opened.append
    ) == published.resolve()
    assert opened == [published.resolve()]
    with pytest.raises(ValueError):
        manager.open_owned_output(current.batch_id, str(source), opened.append)
    with pytest.raises(ValueError, match="已经全部完成"):
        manager.resume(current.batch_id)


def test_a_persisted_running_batch_returns_as_interrupted(tmp_path: Path) -> None:
    source = tmp_path / "a.wav"
    request = BatchRequest.model_validate({"items": [{"input": str(source)}]})
    manager = BatchManager(
        python_executable="python.exe",
        worker_env={},
        process_factory=lambda *_args, **_kwargs: FakeProcess(""),
        history_path=tmp_path / "batches.json",
        output_root=tmp_path / "tasks",
    )
    started = manager.start(request)
    # Simulate a process that disappeared before a terminal protocol event.
    deadline = time.time() + 2
    while manager.snapshot() and manager.snapshot().state == "running" and time.time() < deadline:
        time.sleep(0.01)

    body = started.model_copy(update={"state": "running"})
    (tmp_path / "batches.json").write_text(
        f"[{body.model_dump_json()}]", encoding="utf-8"
    )
    reopened = BatchManager(
        python_executable="python.exe",
        worker_env={},
        history_path=tmp_path / "batches.json",
        output_root=tmp_path / "tasks",
    )

    assert reopened.snapshot() is not None
    assert reopened.snapshot().state == "interrupted"


def test_batch_output_root_can_move_only_while_idle(tmp_path: Path) -> None:
    manager = BatchManager(
        python_executable="python.exe",
        worker_env={},
        history_path=tmp_path / "batches.json",
        output_root=tmp_path / "old",
    )

    manager.set_output_root(tmp_path / "new")

    assert manager.output_root == (tmp_path / "new").resolve()
