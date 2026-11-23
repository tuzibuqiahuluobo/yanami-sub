"""Check both lead-ins against the actual core without ASR or model calls."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from desktop.backend.common.core_compat import unified_llm_contract
from desktop.backend.common.models import TaskRequest
from desktop.backend.worker.main import _execute_pipeline

URL = "https://example.test/watch?v=1"


class ReachedLocalStages(Exception):
    pass


@pytest.fixture
def url_case(tmp_path, monkeypatch):
    if not unified_llm_contract():
        pytest.skip("requires the current unified media contract")
    from finesub import stages
    from finesub.media import source

    monkeypatch.setitem(sys.modules, "finesub.speech.runtime.device",
                        SimpleNamespace(validate_device_token=lambda _: None))
    output = tmp_path / "managed.srt"
    mp4, audio = tmp_path / "video-id.mp4", tmp_path / "video-id.m4a"
    for path in (mp4, audio):
        path.touch()
    downloads = []
    requests = []
    monkeypatch.setattr(source, "resolve_video_id", lambda *_: "video-id")
    def saved(kind, local):
        def fetch(url, _map, *, video_id, target_dir):
            downloads.append((kind, url, video_id, target_dir))
            return video_id, local
        return fetch
    monkeypatch.setattr(source, "download_video", saved("video", mp4))
    monkeypatch.setattr(source, "download_audio", saved("audio", audio))
    monkeypatch.setattr(stages, "source_title_line", lambda _: "视频标题: Sample")
    original = stages._correction_request

    def stop_before_asr(paths, source_path, stage, **options):
        original(paths, source_path, stage, **options)
        requests.append((paths, source_path, options))
        raise ReachedLocalStages

    monkeypatch.setattr(stages, "_correction_request", stop_before_asr)
    return output, mp4, audio, downloads, requests


@pytest.mark.parametrize(("media", "keep", "explicit", "expected_kind", "expected_media"), [
    ("text", True, False, "video", "text"),
    ("audio", True, False, "video", "audio"),
    ("video", True, False, "video", "video"),
    ("text", False, False, "audio", "text"),
    ("video", True, True, "audio", "video"),
])
def test_single_url_uses_local_media_rules(url_case, media, keep, explicit, expected_kind, expected_media):
    from finesub.stages import run_pipeline

    output, mp4, audio, downloads, requests = url_case
    request = TaskRequest(input=URL, output=str(output), stage="final-srt",
                          llm_media=media, llm_retrieval="none", knowledge="none",
                          style_mode="none", llm_video=str(mp4) if explicit else None,
                          download_video_source=keep, extra_info="user note")
    with pytest.raises(ReachedLocalStages):
        _execute_pipeline(request, stage=request.stage, task_id="url", pipeline=run_pipeline)

    assert downloads == [(expected_kind, URL, "video-id", output.parent)]
    paths, local, options = requests[0]
    assert paths.final_srt == output
    assert local == (mp4 if expected_kind == "video" else audio)
    assert options["axes"][0] == expected_media
    assert (Path(options["llm_video"]) if options["llm_video"] else None) == (
        mp4 if expected_media == "video" else None
    )
    assert all(text in options["extra_info"] for text in (URL, "Sample", str(local), "user note"))
    assert "LLM 视频文件:" not in options["extra_info"]


@pytest.mark.parametrize("media", ["text", "video"])
def test_batch_url_uses_same_local_media_rules(url_case, media):
    from finesub.pipeline import build_item

    output, mp4, _audio, downloads, requests = url_case
    item = build_item({"source": URL, "output": str(output), "stage": "final-srt",
                      "llm_media": media, "llm_retrieval": "none", "knowledge": "none", "style_mode": "none"})
    payload = item.stages["download"](None)
    assert payload["audio"] == mp4
    assert payload["llm_video"] is None
    assert payload["_prior_timing"]["download"]["status"] == "executed"
    with pytest.raises(ReachedLocalStages):
        item.stages["llm"](payload)
    assert downloads == [("video", URL, "video-id", output.parent)]
    assert requests[0][2]["axes"][0] == media
    assert requests[0][2]["llm_video"] == (mp4 if media == "video" else None)


def test_explicit_download_hands_off_the_exact_local_file(url_case, monkeypatch):
    from finesub.stages import run_pipeline
    from desktop.backend.worker import media_tools

    output, mp4, _audio, downloads, requests = url_case
    calls = []
    def selected(url, choice, directory):
        calls.append((url, choice.format_id, choice.container, directory))
        return mp4
    monkeypatch.setattr(media_tools, "download_selected_video", selected)
    request = TaskRequest(input=URL, output=str(output), stage="final-srt",
                          link_format={"format_id": "398", "container": "mp4"},
                          llm_media="text", llm_retrieval="none", knowledge="none", style_mode="none")
    with pytest.raises(ReachedLocalStages):
        _execute_pipeline(request, stage=request.stage, task_id="chosen", pipeline=run_pipeline)
    assert calls == [(URL, "398", "mp4", output.parent)]
    assert downloads == []
    assert requests[0][1] == mp4 and requests[0][2]["llm_video"] is None


def test_retry_reuses_the_validated_video_from_the_same_task(tmp_path, monkeypatch):
    if not unified_llm_contract():
        pytest.skip("requires the current unified media contract")
    from finesub import stages
    from finesub.media import source

    mp4 = tmp_path / "video-id.mp4"
    mp4.write_bytes(b"cached download")
    checked = []
    monkeypatch.setattr(source, "resolve_video_id", lambda *_: "video-id")
    monkeypatch.setattr(source, "validate_video_audio_coverage", checked.append)
    monkeypatch.setattr(stages, "source_title_line", lambda _: "")
    monkeypatch.setitem(sys.modules, "yt_dlp", None)  # A second download must not start.
    request = TaskRequest(input=URL, output=str(tmp_path / "managed.srt"),
                          stage="final-srt", knowledge="none", style_mode="none", llm_media="text")
    for _ in range(2):
        chosen, _, _ = stages.prepare_url_input(request.input, output_path=request.output, llm_video=None)
        assert chosen == mp4
    assert checked == [mp4, mp4]
    assert mp4.read_bytes() == b"cached download"
