from desktop.backend.worker.protocol import EventLogWriter
import pytest


def test_ytdlp_can_write_to_worker_log():
    write_string = pytest.importorskip("yt_dlp.utils").write_string

    events = []
    stream = EventLogWriter("test", events.append)
    write_string("字幕 download\n", out=stream)
    assert len(events) == 1
    assert "字幕 download" in events[0].payload["message"]
