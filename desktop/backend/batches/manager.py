from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any

from finesub_bootstrap.locks import TASK_ACTIVITY_ROOT_VARIABLE
from finesub_bootstrap.processes import terminate_process_tree
from finesub_bootstrap import task_output

from desktop.backend.batches.protocol import BatchWorkerEvent, parse_batch_event
from desktop.backend.common.models import (
    BatchItemRequest,
    BatchItemSnapshot,
    BatchRequest,
    BatchSnapshot,
)
from desktop.backend.jobs.launch import (
    ProcessFactory,
    ProcessTerminator,
    WorkerLaunchContext,
    device_environment,
    task_stem,
)


LOGGER = logging.getLogger(__name__)


class BatchAlreadyRunning(RuntimeError):
    pass


class BatchNotFound(KeyError):
    pass


class BatchManager:
    """Own one isolated core scheduler process and its durable GUI view."""

    HISTORY_LIMIT = 50

    def __init__(
        self,
        *,
        python_executable: str | Path,
        worker_env: Mapping[str, str],
        working_directory: str | Path | None = None,
        available_gpus: Callable[[], Any] = lambda: None,
        process_factory: ProcessFactory = subprocess.Popen,
        terminate_process_tree: ProcessTerminator = terminate_process_tree,
        history_path: str | Path,
        output_root: str | Path,
    ) -> None:
        self._worker_context = WorkerLaunchContext(
            python_executable=str(python_executable),
            working_directory=(
                str(working_directory) if working_directory is not None else None
            ),
            environment=dict(worker_env),
        )
        self.process_factory = process_factory
        self.available_gpus = available_gpus
        self.terminate_process_tree = terminate_process_tree
        self.history_path = Path(history_path).expanduser().resolve()
        self.output_root = Path(output_root).expanduser().resolve()
        self._lock = threading.RLock()
        self._process: Any | None = None
        self._snapshot: BatchSnapshot | None = None
        self._history: list[BatchSnapshot] = []
        self._load_history()

    def set_worker_context(self, context: WorkerLaunchContext) -> None:
        with self._lock:
            self._worker_context = context

    def set_output_root(self, output_root: str | Path) -> None:
        """Retarget future batches after the core moves its data store."""

        with self._lock:
            self._ensure_idle()
            self.output_root = Path(output_root).expanduser().resolve()

    def start(self, request: BatchRequest) -> BatchSnapshot:
        with self._lock:
            self._ensure_idle()
            batch_id = task_output.new_task_id("batch")
            resolved = self._resolve_outputs(batch_id, request)
            process = self._spawn(batch_id, resolved)
            now = time.time()
            snapshot = BatchSnapshot(
                batch_id=batch_id,
                state="running",
                request=resolved,
                items=self._initial_items(resolved),
                created_at=now,
                updated_at=now,
                log_path=str(self._batch_dir(batch_id) / "batch-log.txt"),
                status_path=str(self._batch_dir(batch_id) / "batch-status.jsonl"),
            )
            self._process = process
            self._snapshot = snapshot
            self._history.append(snapshot)
            self._persist_history()
            self._start_reader(batch_id, process)
            return snapshot.model_copy(deep=True)

    def resume(self, batch_id: str) -> BatchSnapshot:
        with self._lock:
            self._ensure_idle()
            snapshot = self._find(batch_id)
            if snapshot.state == "completed" and all(
                item.state == "done" for item in snapshot.items
            ):
                raise ValueError("这个批次已经全部完成。")
            process = self._spawn(batch_id, snapshot.request)
            snapshot.state = "running"
            snapshot.error = ""
            snapshot.updated_at = time.time()
            snapshot.items = self._initial_items(snapshot.request)
            self._process = process
            self._snapshot = snapshot
            self._history.remove(snapshot)
            self._history.append(snapshot)
            self._persist_history()
            self._start_reader(batch_id, process)
            return snapshot.model_copy(deep=True)

    def cancel(self, batch_id: str) -> BatchSnapshot:
        with self._lock:
            snapshot = self._find(batch_id)
            if (
                snapshot.state != "running"
                or self._process is None
                or self._process.poll() is not None
            ):
                return snapshot.model_copy(deep=True)
            snapshot.state = "cancelled"
            snapshot.updated_at = time.time()
            process = self._process
            self._persist_history()
        self.terminate_process_tree(process)
        return snapshot.model_copy(deep=True)

    def shutdown(self) -> None:
        with self._lock:
            snapshot = self._snapshot
            process = self._process
            if (
                snapshot is None
                or snapshot.state != "running"
                or process is None
                or process.poll() is not None
            ):
                return
            snapshot.state = "interrupted"
            snapshot.error = "应用退出时批次被中断，可以继续批次。"
            snapshot.updated_at = time.time()
            self._persist_history()
        try:
            self.terminate_process_tree(process)
        except OSError:
            pass

    def snapshot(self) -> BatchSnapshot | None:
        with self._lock:
            return self._snapshot.model_copy(deep=True) if self._snapshot else None

    def history(self) -> list[BatchSnapshot]:
        with self._lock:
            return [item.model_copy(deep=True) for item in reversed(self._history)]

    def request_for(self, batch_id: str) -> BatchRequest:
        with self._lock:
            return self._find(batch_id).request.model_copy(deep=True)

    def is_running(self) -> bool:
        with self._lock:
            return bool(
                self._snapshot is not None
                and self._snapshot.state == "running"
                and self._process is not None
                and self._process.poll() is None
            )

    def open_batch_directory(
        self, batch_id: str, opener: Callable[[Path], None]
    ) -> Path:
        with self._lock:
            snapshot = self._find(batch_id)
            target = self._batch_dir(snapshot.batch_id)
            target.mkdir(parents=True, exist_ok=True)
        opener(target)
        return target

    def open_owned_output(
        self, batch_id: str, output_path: str, opener: Callable[[Path], None]
    ) -> Path:
        with self._lock:
            snapshot = self._find(batch_id)
            target = Path(output_path).expanduser().resolve()
            allowed = {
                Path(value).expanduser().resolve()
                for item in snapshot.items
                for value in item.outputs.values()
            }
            if target not in allowed or not target.is_file():
                raise ValueError("path is not a published output of this batch")
        opener(target)
        return target

    def open_log(self, batch_id: str, opener: Callable[[Path], None]) -> Path:
        with self._lock:
            snapshot = self._find(batch_id)
            target = Path(snapshot.log_path).expanduser().resolve()
            if target.parent != self._batch_dir(snapshot.batch_id).resolve():
                raise ValueError("batch log escaped its owned directory")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=True)
        opener(target)
        return target

    def _resolve_outputs(self, batch_id: str, request: BatchRequest) -> BatchRequest:
        items: list[BatchItemRequest] = []
        for index, item in enumerate(request.items):
            if item.output:
                items.append(item)
                continue
            stem = task_stem(item)
            output = self._batch_dir(batch_id) / f"{index + 1:03d}-{stem}" / f"{stem}.srt"
            items.append(item.model_copy(update={"output": str(output)}))
        return request.model_copy(update={"items": items})

    @staticmethod
    def _initial_items(request: BatchRequest) -> list[BatchItemSnapshot]:
        return [
            BatchItemSnapshot(
                index=index,
                input=item.input,
                label=Path(item.input).name or item.input,
            )
            for index, item in enumerate(request.items)
        ]

    def _spawn(self, batch_id: str, request: BatchRequest) -> Any:
        context = self._worker_context
        environment = os.environ.copy()
        environment.update(context.environment)
        pinned, _notice = device_environment(request.items[0], self.available_gpus)
        environment.update(pinned)
        environment["FINESUB_DESKTOP_BATCH_ROOT"] = str(self._batch_dir(batch_id))
        environment[TASK_ACTIVITY_ROOT_VARIABLE] = str(self.history_path.parent)
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt"
            else 0
        )
        process = self.process_factory(
            [
                context.python_executable,
                "-m",
                "desktop.backend.worker.batch_main",
                "--batch-id",
                batch_id,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=environment,
            cwd=context.working_directory,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("batch worker process pipes were not created")
        process.stdin.write(request.model_dump_json() + "\n")
        process.stdin.flush()
        return process

    def _start_reader(self, batch_id: str, process: Any) -> None:
        threading.Thread(
            target=self._read_worker,
            args=(batch_id, process),
            daemon=True,
        ).start()

    def _read_worker(self, batch_id: str, process: Any) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            event = parse_batch_event(line, batch_id=batch_id)
            with self._lock:
                snapshot = self._snapshot
                if snapshot is None or snapshot.batch_id != batch_id:
                    continue
                self._apply_event(snapshot, event)
                snapshot.updated_at = time.time()
                self._persist_history()
        return_code = process.wait()
        with self._lock:
            snapshot = self._snapshot
            if snapshot is not None and snapshot.batch_id == batch_id:
                if snapshot.state == "running":
                    snapshot.state = "failed"
                    snapshot.error = f"批处理进程意外退出（代码 {return_code}）。"
                    snapshot.updated_at = time.time()
                if self._process is process:
                    self._process = None
                self._persist_history()

    def _apply_event(self, snapshot: BatchSnapshot, event: BatchWorkerEvent) -> None:
        if event.type == "snapshot":
            rows = event.payload.get("items", [])
            snapshot.items = [BatchItemSnapshot.model_validate(row) for row in rows]
        elif event.type == "completed":
            rows = event.payload.get("items", [])
            if isinstance(rows, list):
                snapshot.items = [BatchItemSnapshot.model_validate(row) for row in rows]
            snapshot.state = "completed"
        elif event.type == "failed":
            snapshot.state = "failed"
            snapshot.error = str(event.payload.get("message") or "批处理失败。")
        elif event.type == "log":
            message = str(event.payload.get("message") or "")
            if message:
                self._append_log(snapshot, message)

    @staticmethod
    def _append_log(snapshot: BatchSnapshot, message: str) -> None:
        path = Path(snapshot.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip("\r\n") + "\n")

    def _ensure_idle(self) -> None:
        if self.is_running():
            raise BatchAlreadyRunning("a batch is already running")

    def _find(self, batch_id: str) -> BatchSnapshot:
        for snapshot in self._history:
            if snapshot.batch_id == batch_id:
                return snapshot
        raise BatchNotFound(batch_id)

    def _batch_dir(self, batch_id: str) -> Path:
        return self.output_root / batch_id

    def _load_history(self) -> None:
        if not self.history_path.is_file():
            return
        try:
            body = json.loads(self.history_path.read_text(encoding="utf-8"))
            rows = body if isinstance(body, list) else []
            self._history = [BatchSnapshot.model_validate(row) for row in rows]
        except (OSError, ValueError):
            self._history = []
        if self._history:
            self._snapshot = self._history[-1]
            if self._snapshot.state == "running":
                self._snapshot.state = "interrupted"
                self._snapshot.error = "上次运行意外中断，可以继续批次。"
                self._snapshot.updated_at = time.time()
                self._persist_history()

    def _persist_history(self) -> None:
        temporary = self.history_path.with_name(
            f".{self.history_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            rows = self._history[-self.HISTORY_LIMIT :]
            temporary.write_text(
                json.dumps(
                    [row.model_dump(mode="json") for row in rows],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(temporary, self.history_path)
        except OSError:
            # State publication is ancillary to the run. A transient antivirus
            # or filesystem lock must not kill the reader thread and turn a
            # completed core batch into an apparent crash.
            LOGGER.exception("could not write the batch history")
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
