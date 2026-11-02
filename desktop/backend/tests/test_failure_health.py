from io import StringIO
from pathlib import Path

import pytest

from desktop.backend.jobs.manager import JobManager
from desktop.backend.batches.manager import BatchManager
from desktop.backend.common.models import TaskRequest, BatchRequest
from desktop.backend.worker.protocol import WorkerEvent, encode_event
from desktop.backend.batches.protocol import BatchWorkerEvent, encode_batch_event
from finesub_bootstrap.locks import active_run_count


class Process:
    def __init__(self, output):
        self.stdin, self.stdout = StringIO(), StringIO(output)
    def poll(self):
        return 1
    def wait(self):
        return 1


@pytest.mark.parametrize("terminal,expected", [("failed", 1), ("crash", 1), ("completed", 0), ("cancelled", 0)])
def test_single_failure_check_runs_once_without_replacing_task_error(tmp_path, monkeypatch, terminal, expected):
    root = tmp_path / "user-data"
    calls, readers = [], []
    def check():
        assert active_run_count(root) > 0
        calls.append(True)
        return "RUNTIME CHECK NOTE / 环境核对"
    def factory(argv, **kwargs):
        task_id = argv[-1]
        event = WorkerEvent.log(task_id, "original task error") if terminal == "crash" else WorkerEvent(
            type=terminal, task_id=task_id, payload={"message": "original task error", "outputs": {}})
        return Process(encode_event(event))
    manager = JobManager(python_executable="python.exe", worker_env={}, process_factory=factory,
        history_path=root / "tasks.json", output_root=tmp_path / "tasks", on_runtime_failure=check)
    monkeypatch.setattr(manager, "_start_reader", lambda *args: readers.append(args))
    started = manager.start(TaskRequest(input="audio.wav"))
    manager._read_worker(*readers[0])
    assert len(calls) == expected and active_run_count(root) == 0
    current = manager.snapshot()
    if expected:
        assert current.state == "failed" and current.error == "original task error"
        log = (tmp_path / "tasks" / started.task_id / "task-log.txt").read_text(encoding="utf-8")
        assert log.count("RUNTIME CHECK NOTE") == 1 and "original task error" in log
    manager.history(); manager.snapshot()
    assert len(calls) == expected


@pytest.mark.parametrize("terminal,expected", [("failed", 1), ("partial", 1), ("completed", 0), ("cancelled", 0)])
def test_batch_failure_check_includes_partial_failures_but_not_cancellation(tmp_path, monkeypatch, terminal, expected):
    root, readers, calls = tmp_path / "user-data", [], []
    def check():
        assert active_run_count(root) > 0
        calls.append(True)
        return "BATCH RUNTIME CHECK / 批次核对"
    def factory(argv, **kwargs):
        batch_id = argv[-1]
        if terminal == "failed":
            event = BatchWorkerEvent(type="failed", batch_id=batch_id, payload={"message": "original batch error"})
        else:
            rows = manager._initial_items(request)
            rows[0] = rows[0].model_copy(update={"state": "failed" if terminal == "partial" else "done"})
            event = BatchWorkerEvent(type="completed", batch_id=batch_id, payload={"items": [row.model_dump(mode="json") for row in rows]})
        return Process("" if terminal == "cancelled" else encode_batch_event(event))
    manager = BatchManager(python_executable="python.exe", worker_env={}, process_factory=factory,
        history_path=root / "batches.json", output_root=tmp_path / "batches", on_runtime_failure=check)
    monkeypatch.setattr(manager, "_start_reader", lambda *args: readers.append(args))
    request = BatchRequest.model_validate({"items": [{"input": "audio.wav"}]})
    started = manager.start(request)
    if terminal == "cancelled":
        manager._snapshot.state = "interrupted"
    manager._read_worker(*readers[0])
    assert len(calls) == expected and active_run_count(root) == 0
    if terminal == "failed":
        assert manager.snapshot().error == "original batch error"
    if expected:
        assert "BATCH RUNTIME CHECK" in Path(started.log_path).read_text(encoding="utf-8")


def test_check_callback_error_cannot_replace_original_failure(tmp_path, monkeypatch):
    root, readers = tmp_path / "user-data", []
    def fail():
        raise RuntimeError("diagnostic failed")
    manager = JobManager(python_executable="python.exe", worker_env={},
        process_factory=lambda argv, **kwargs: Process(encode_event(WorkerEvent.failed(argv[-1], "original error"))),
        history_path=root / "tasks.json", output_root=tmp_path / "tasks", on_runtime_failure=fail)
    monkeypatch.setattr(manager, "_start_reader", lambda *args: readers.append(args))
    manager.start(TaskRequest(input="audio.wav"))
    manager._read_worker(*readers[0])
    assert manager.snapshot().state == "failed" and manager.snapshot().error == "original error"
    assert active_run_count(root) == 0


def test_old_batch_reader_cannot_check_or_mutate_a_resumed_process(tmp_path, monkeypatch):
    calls, readers = [], []
    manager = BatchManager(python_executable="python.exe", worker_env={},
        process_factory=lambda argv, **kwargs: Process(encode_batch_event(BatchWorkerEvent(
            type="failed", batch_id=argv[-1], payload={"message": "obsolete error"}))),
        history_path=tmp_path / "batches.json", output_root=tmp_path / "tasks",
        on_runtime_failure=lambda: calls.append(True) or "stale note")
    monkeypatch.setattr(manager, "_start_reader", lambda *args: readers.append(args))
    first = manager.start(BatchRequest.model_validate({"items": [{"input": "audio.wav"}]}))
    manager.resume(first.batch_id)
    new_process = manager._process
    manager._read_worker(*readers[0])
    assert manager._process is new_process and manager.snapshot().state == "running" and not calls
    manager.on_runtime_failure = None
    manager._read_worker(*readers[1])
    assert not manager._runtime_activities
