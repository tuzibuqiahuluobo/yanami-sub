from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from desktop.backend.jobs.task_log import TaskLog
from desktop.backend.worker.main import WorkerReporter
from desktop.backend.worker.protocol import (
    WorkerEvent,
    decode_event,
    encode_event,
    parse_worker_line,
)


def test_event_round_trip_is_one_json_line() -> None:
    event = WorkerEvent.progress(
        "task-1",
        stage="aligned",
        message="语音识别",
    )

    encoded = encode_event(event)

    assert encoded.endswith("\n")
    assert "\n" not in encoded[:-1]
    assert decode_event(encoded) == event


def test_non_protocol_worker_output_becomes_log_event() -> None:
    event = parse_worker_line("Loading model...\n", task_id="task-1")

    assert event.type == "log"
    assert event.task_id == "task-1"
    assert event.payload["message"] == "Loading model..."


def test_native_windows_log_and_utf8_events_share_one_pipe_without_mojibake(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("locale.getencoding", lambda: "cp936")
    task_id = "task-1"
    source = (
        "import sys; "
        "sys.stdout.buffer.write('正在创建库 Library café\\n'.encode('cp936')); "
        "sys.stdout.buffer.write('翻译 Translation / 日本語 ✅\\n'.encode('utf-8'))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", source],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert process.stdout is not None
    events = [parse_worker_line(line, task_id=task_id) for line in process.stdout]
    assert process.wait() == 0
    assert [event.payload["message"] for event in events] == [
        "正在创建库 Library café",
        "翻译 Translation / 日本語 ✅",
    ]
    log = TaskLog(tmp_path)
    for event in events:
        log.append(event)
    log.finish()
    saved = (tmp_path / "task-log.txt").read_text(encoding="utf-8")
    assert "正在创建库 Library café" in saved
    assert "翻译 Translation / 日本語 ✅" in saved
    assert "�" not in saved


def test_protocol_event_uses_frontend_camel_case_keys() -> None:
    encoded = encode_event(WorkerEvent.started("task-1"))

    assert '"taskId":"task-1"' in encoded
    assert "task_id" not in encoded


def test_every_subtitle_stage_keeps_mixed_language_wire_and_file_logs(
    tmp_path: Path,
) -> None:
    stages = [
        ("vocal", "人声分离 Voice separation"),
        ("aligned", "语音识别 Recognition"),
        ("stable", "字幕稳定化 Stabilization"),
        ("raw-srt", "原始字幕 Raw subtitle"),
        ("translated-srt", "纠错翻译 Translation"),
        ("final-srt", "最终字幕 Final subtitle ✅"),
    ]
    events: list[WorkerEvent] = []
    reporter = WorkerReporter("task-1", events.append)
    for stage, detail in stages:
        reporter.stage_started(stage, detail=detail)
        reporter.summary(stage, {"进度 Progress": f"{detail} / café / 日本語"})

    task_log = TaskLog(tmp_path)
    round_tripped = []
    for event in events:
        received = parse_worker_line(
            encode_event(event).encode("utf-8").decode("utf-8"), task_id="task-1"
        )
        round_tripped.append(received)
        task_log.append(received)
    task_log.finish()

    assert round_tripped == events
    assert [event.payload["stage"] for event in events if event.type == "stage"] == [
        stage for stage, _ in stages
    ]
    saved = (tmp_path / "task-log.txt").read_text(encoding="utf-8")
    for _, detail in stages:
        assert detail in saved
    assert "�" not in saved
