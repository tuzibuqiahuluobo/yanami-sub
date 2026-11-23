import io
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from desktop.backend.common.models import LinkFormat, TaskRequest
from desktop.backend.worker import media_tools


def test_discovery_does_not_list_audio_only_drm_or_unmergeable_video():
    rows = [
        dict(format_id="140", ext="m4a", vcodec="none", acodec="aac"),
        dict(format_id="398", ext="mp4", vcodec="av1", acodec="none", height=720, fps=60),
        dict(format_id="135", ext="mp4", vcodec="h264", acodec="none", height=480, fps=29.97),
        dict(format_id="aac", ext="webm", vcodec="none", acodec="opus", has_drm=True),
        dict(format_id="250", ext="webm", vcodec="vp9", acodec="none", height=720, fps=50),
        dict(format_id="unknown", ext="mp4", vcodec="av1", height=1080, fps=60),
        dict(format_id="x", ext="mp4", vcodec="av1", acodec="aac", height=2160, fps=60, has_drm=True),
        dict(format_id="malicious]", ext="mp4", vcodec="av1", acodec="aac", height=1440, fps=60),
    ]
    assert [row["format_id"] for row in media_tools.video_formats({"formats": rows})] == ["398", "135"]


def test_exact_download_keeps_container_and_reuses_only_its_cache(tmp_path, monkeypatch):
    from finesub.media import ffmpeg, source

    rows = [
        dict(format_id="140", ext="m4a", vcodec="none", acodec="aac"),
        dict(format_id="398", ext="mp4", vcodec="av1", acodec="none", height=1080, fps=60),
        dict(format_id="398-1", ext="mp4", vcodec="h264", acodec="none", height=720, fps=30),
        dict(format_id="399", ext="mp4", vcodec="h264", acodec="aac", height=480, fps=30),
    ]
    picked = []
    class Download:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def download(self, urls):
            assert urls == [url]
            with YoutubeDL({"quiet": True, "cachedir": False, "format": options[-1]["format"]}) as real:
                info = real.process_ie_result({"id": "clip", "title": "Clip", "formats": [
                    {**row, "url": f"https://example.test/{row['format_id']}.{row['ext']}"} for row in rows
                ]}, download=False)
            picked.append(info["format_id"])
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
    third = media_tools.download_selected_video(url, LinkFormat(format_id="398-1", container="mp4"), tmp_path)
    assert len({first, second, third}) == 3 and picked == ["398+140", "399", "398-1+140"]


@pytest.mark.parametrize(
    ("message", "error_type", "expected"),
    [
        ("Requested format is not available.", ValueError, "恢复自动"),
        ("HTTP Error 429: Too Many Requests", DownloadError, "HTTP Error 429"),
    ],
)
def test_failed_selection_never_silently_falls_back(tmp_path, monkeypatch, message, error_type, expected):
    from finesub.media import ffmpeg

    attempts = []
    def download(urls):
        attempts.extend(urls)
        raise DownloadError(message)

    monkeypatch.setattr(ffmpeg, "resolve_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(media_tools, "downloader", lambda **_: nullcontext(SimpleNamespace(download=download)))
    url = "https://www.youtube.com/watch?v=abcdefg"
    with pytest.raises(error_type, match=expected):
        media_tools.download_selected_video(url, LinkFormat(format_id="399", container="mp4"), tmp_path)
    assert attempts == [url]


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
