import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.backend.common.models import LinkFormat, TaskRequest
from desktop.backend.worker import media_tools


def test_discovery_does_not_list_audio_only_drm_or_unmergeable_video():
    rows = [
        dict(format_id="140", ext="m4a", vcodec="none", acodec="aac"),
        dict(format_id="398", ext="mp4", vcodec="av1", acodec="none", height=720, fps=60),
        dict(format_id="135", ext="mp4", vcodec="h264", acodec="none", height=480, fps=29.97),
        dict(format_id="250", ext="webm", vcodec="vp9", acodec="none", height=720, fps=50),
        dict(format_id="x", ext="mp4", vcodec="av1", acodec="aac", height=2160, fps=60, has_drm=True),
        dict(format_id="malicious]", ext="mp4", vcodec="av1", acodec="aac", height=1440, fps=60),
    ]
    assert [row["format_id"] for row in media_tools.video_formats({"formats": rows})] == ["398", "135"]


def test_exact_download_keeps_container_and_reuses_only_its_cache(tmp_path, monkeypatch):
    from finesub.media import ffmpeg, source

    calls = []
    class Download:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def download(self, urls):
            calls.append(urls)
            Path(options[-1]["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(b"video")
    options = []
    monkeypatch.setattr(media_tools, "downloader", lambda **kwargs: (options.append(kwargs) or Download()))
    monkeypatch.setattr(ffmpeg, "resolve_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(ffmpeg, "resolve_ffprobe", lambda: "ffprobe")
    monkeypatch.setattr(ffmpeg, "run_capture", lambda _: SimpleNamespace(stdout=json.dumps(
        {"streams": [{"codec_type": "audio"}, {"codec_type": "video"}]})))
    monkeypatch.setattr(source, "validate_video_audio_coverage", lambda _: None)
    url = "https://www.youtube.com/watch?v=abcdefg"
    first = media_tools.download_selected_video(url, LinkFormat(format_id="398", container="mp4"), tmp_path)
    assert media_tools.download_selected_video(url, LinkFormat(format_id="398", container="mp4"), tmp_path) == first
    second = media_tools.download_selected_video(url, LinkFormat(format_id="399", container="mp4"), tmp_path)
    assert first != second and len(calls) == 2
    assert options[0]["format"] == "best[format_id=398][ext=mp4][vcodec!=none]/bestvideo[format_id=398][ext=mp4][vcodec!=none]+ba[ext=m4a]"


def test_subtitle_export_selects_track_and_never_overwrites(tmp_path, monkeypatch):
    class Ydl:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def extract_info(self, url, *, download):
            assert not download
            return {"title": "demo", "subtitles": {"ja": [{"ext": "srt", "url": "https://example.test/original"}]},
                    "automatic_captions": {
                        "ja": [{"ext": "srt", "url": "https://example.test/auto"}],
                        "zh": [{"ext": "vtt", "url": "https://example.test/auto?tlang=zh"}],
                    }}
        def urlopen(self, url):
            assert url.endswith("/original")
            return io.BytesIO("1\n00:00:00,000 --> 00:00:01,000\nこんにちは\n".encode())
    monkeypatch.setattr(media_tools, "downloader", lambda **_: Ydl())
    url = "https://www.youtube.com/watch?v=abcdefg"
    tracks = media_tools.inspect_link(url, captions=True)["tracks"]
    assert [(row["language"], row["automatic"]) for row in tracks] == [("ja", False), ("ja", True)]
    assert all("url" not in row for row in tracks)
    target = tmp_path / "caption.txt"
    media_tools.save_subtitle(url, "ja", False, "txt", str(target))
    assert target.read_text(encoding="utf-8") == "こんにちは\n"
    with pytest.raises(ValueError, match="File exists"):
        media_tools.save_subtitle(url, "ja", False, "txt", str(target))
    assert target.read_text(encoding="utf-8") == "こんにちは\n"


def test_subtitle_source_is_explicit_and_format_id_is_not_a_selector_expression():
    for bad in ("file:///etc/passwd", "https://youtube.com@example.test/watch", "https://example.test"):
        with pytest.raises(ValueError):
            media_tools.inspect_link(bad, captions=True)
    with pytest.raises(ValueError):
        LinkFormat(format_id="398]/best", container="mp4")
    with pytest.raises(ValueError):
        TaskRequest(input="clip.mp4", link_format={"format_id": "398", "container": "mp4"})
