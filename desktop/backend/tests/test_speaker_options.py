from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.backend.common.models import BatchItemRequest, TaskRequest
from desktop.backend.worker import main as worker
from desktop.backend.worker.batch_main import _item_options


@pytest.mark.parametrize("mode", ["off", "acoustics", "judge-text", "judge-audio"])
def test_speaker_options_reach_single_and_batch(monkeypatch, tmp_path: Path, mode: str):
    monkeypatch.setattr(worker, "_prepare_task_knowledge", lambda *args, **kwargs: None)
    values = dict(input=str(tmp_path / "中文_日本語.mp4"), stage="final-srt", diarize=mode,
                  diarize_backend="nemotron3", diarize_max_speakers=4,
                  speaker_tracks="both" if mode != "off" else "off")
    request = TaskRequest(**values)
    result = worker._execute_pipeline(request, stage=request.stage, task_id="speaker-test",
                                      pipeline=lambda _input, **kwargs: kwargs)
    batch = _item_options(BatchItemRequest(**values), {"asr": 1, "llm": 1}, task_id="speaker-batch")
    for key in ("diarize", "diarize_backend", "diarize_max_speakers", "speaker_tracks"):
        assert result[key] == values[key]
        assert batch[key] == values[key]


def test_speaker_defaults_are_opt_in_and_validate():
    request = TaskRequest(input="clip.mp4")
    assert request.diarize == request.speaker_tracks == "off"
    assert request.diarize_backend is None and request.diarize_max_speakers is None
    for patch in ({"diarize": "on"}, {"diarize_backend": "unknown"}, {"diarize_max_speakers": 0},
                  {"speaker_tracks": "both"}):
        with pytest.raises(ValueError):
            TaskRequest(input="clip.mp4", **patch)


def test_speaker_publication_preserves_user_files_and_missing_exports(monkeypatch, tmp_path):
    source = tmp_path / "中文.mp4"
    source.write_bytes(b"media")
    root = tmp_path / "artifacts"
    root.mkdir()
    paths = SimpleNamespace(raw_srt=root / "clip-raw.srt", stable_json=root / "clip-stable.json")
    paths.raw_srt.write_text("subtitles", "utf-8")
    folder = root / "clip-speakers"
    folder.mkdir()
    (folder / "s1.srt").write_text("speaker subtitles", "utf-8")
    (folder / "all.ass").write_text("speaker ass", "utf-8")
    (folder / "debug.json").write_text("{}", "utf-8")
    edited = tmp_path / "中文-s1.srt"
    edited.write_text("user edit", "utf-8")
    monkeypatch.setattr(worker, "_claimed_outputs", lambda: {})
    monkeypatch.setattr(worker, "_record_published_output", lambda *args: None)
    request = TaskRequest(input=str(source), diarize="acoustics", speaker_tracks="both")
    outputs = worker._publish_output(paths, request, task_id="speaker-publish")
    assert set(outputs) == {"rawSrt", "speaker:s1.srt", "speaker:all.ass"}
    assert edited.read_text("utf-8") == "user edit"
    assert Path(outputs["speaker:s1.srt"]).read_text("utf-8") == "speaker subtitles"
    assert Path(outputs["speaker:s1.srt"]) != edited
    assert Path(outputs["speaker:all.ass"]).parent == source.parent
    assert set(worker._publish_output(paths, request.model_copy(update={"speaker_tracks": "off"}), task_id="off")) == {"rawSrt"}


def test_missing_optional_speech_outputs_are_reported_as_skipped(tmp_path, monkeypatch):
    paths = SimpleNamespace(raw_srt=tmp_path / "clip-raw.srt", stable_json=tmp_path / "clip-stable.json",
        final_srt=tmp_path / "clip.srt")
    paths.raw_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n中文 日本語\n", encoding="utf-8")
    events = []
    request = TaskRequest(input="https://example.com/clip", diarize="acoustics", speaker_tracks="both", knowledge="none", cleanup_intermediate=False)
    worker.run_request(request, task_id="optional-skipped", pipeline=lambda *_args, **_kwargs: paths, emit=events.append)
    skipped = [event.payload["stage"] for event in events if event.type == "stage" and event.payload.get("skipped")]
    assert skipped == ["diarize", "speaker-tracks"]
    assert events[-1].type == "completed"
