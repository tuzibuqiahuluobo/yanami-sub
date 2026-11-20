from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from desktop.backend.common import programme_reference as reference
from desktop.backend.common.models import BatchRequest, TaskRequest
from desktop.backend.common.subtitle_roles import describe_roles, export_roles, translated_rows
from desktop.backend.jobs.cooperation import invoke_worker
from desktop.backend.worker import programme_reference as worker
from finesub.llm import correction_translation
from finesub.llm.prompts import ContextPack, WindowContextNote
from finesub.subtitles.model import parse_srt


@pytest.fixture
def media(tmp_path, monkeypatch):
    clip, reaction, subtitle = [tmp_path / name for name in ("cut.mp4", "host.mkv", "programme.srt")]
    clip.touch()
    reaction.touch()
    subtitle.write_bytes(("1\n00:10:01,000 --> 00:10:03,000\n节目 <tag> | text\n\n"
                          "2\n00:10:05,000 --> 00:10:06,000\n第二句\n").encode("utf-8-sig"))
    monkeypatch.setattr(reference, "_video_duration_ms",
                        lambda path, **_: 8_000 if path == clip else 60_000)
    settings = reference.ProgrammeReference(
        clip=str(clip), subtitle=str(subtitle), subtitle_offset_ms=600_000,
        spans=[dict(clip_ms=2_000, reaction_ms=15_000, length_ms=5_000),
               dict(clip_ms=2_000, reaction_ms=30_000, length_ms=5_000)],
    )
    return settings, reaction


def test_align_full_programme_srt_with_cut_boundary_and_replay(media):
    settings, reaction = media
    rows, duration = reference.load_alignment(settings, str(reaction))
    assert duration == 8_000
    assert [(row.start, row.end) for row in rows] == [(15, 16), (18, 19), (30, 31), (33, 34)]
    assert [row.text for row in rows] == ["节目 <tag> | text", "第二句"] * 2


def test_reject_overlap_and_ranges_past_either_video(media):
    settings, reaction = media
    payload = settings.model_dump()
    payload["spans"][1]["reaction_ms"] = 16_000
    with pytest.raises(ValueError, match="must not overlap"):
        reference.ProgrammeReference.model_validate(payload)
    payload["spans"][1]["reaction_ms"] = 58_000
    with pytest.raises(ValueError, match="Range 2 extends beyond the reaction video"):
        reference.load_alignment(reference.ProgrammeReference.model_validate(payload), str(reaction))
    payload["spans"][1].update(clip_ms=4_000, reaction_ms=40_000)
    with pytest.raises(ValueError, match="Range 2 extends beyond the clip"):
        reference.load_alignment(reference.ProgrammeReference.model_validate(payload), str(reaction))


def test_reference_only_reaches_matching_correction_window(tmp_path, media, monkeypatch):
    settings, reaction = media
    output = tmp_path / "task.srt"
    request = TaskRequest(input=str(reaction), programme_reference=settings)
    note = WindowContextNote("research", "s1", "s2", "original research")
    pack = ContextPack(window_contexts=(note,))
    rows = [SimpleNamespace(id=f"s{i}", start=start, end=end) for i, (start, end) in
            enumerate([(1, 2), (15, 16), (30, 31), (40, 42)], 1)]
    plan = SimpleNamespace(windows=[
        SimpleNamespace(segments=[row], overlap_segments=[]) for row in rows
    ])
    monkeypatch.setattr(correction_translation, "execute_correction_windows",
                        lambda **kwargs: kwargs["context_pack"])

    def correct(**_):
        return correction_translation.execute_correction_windows(plan=plan, context_pack=pack)

    with worker.programme_scope(request, stage="final-srt", output=str(output)):
        result = correct()
    assert [row.first_source_id for row in result.window_contexts] == ["s2", "s3", "s1"]
    assert "＜tag＞ ｜ text" in result.window_contexts[0].context
    assert "节目参考台词" in result.window_contexts[0].context
    assert result.window_contexts[-1] == note
    assert correct() is pack
    assert len(parse_srt(worker.reference_output(output).read_text(encoding="utf-8"))) == 4
    with worker.programme_scope(request, stage="translated-srt", output=str(output)):
        assert correct() == result
    with pytest.raises(ValueError, match="disable its programme reference"):
        with worker.programme_scope(TaskRequest(input=str(reaction)), stage="final-srt", output=str(output)):
            pytest.fail("must not rerun with a different context")
    with worker.programme_scope(request, stage="raw-srt", output=str(output)):
        assert correct() is pack


def test_reference_is_not_persisted_for_ordinary_tasks_or_accepted_in_batch(media):
    settings, reaction = media
    request = TaskRequest(input=str(reaction))
    assert "programme_reference" not in request.model_dump(mode="json")
    payload = request.model_dump() | {"programme_reference": settings.model_dump()}
    with pytest.raises(ValueError, match="only available for single tasks"):
        BatchRequest(items=[payload])


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg not on PATH")
def test_preview_uses_real_video_through_runtime_process(tmp_path):
    clip = tmp_path / "节目.mp4"
    reaction = tmp_path / "主播.mp4"
    subtitle = tmp_path / "节目.srt"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=32x32:r=5:d=4",
                    "-threads", "1", "-c:v", "mpeg4", str(clip)], check=True, timeout=15)
    shutil.copyfile(clip, reaction)
    subtitle.write_bytes("1\n00:00:01,000 --> 00:00:02,000\n节目台词\n".encode("utf-16"))
    context = SimpleNamespace(python_executable=sys.executable, environment={}, working_directory=None)
    payload = {"action": "preview", "reaction": str(reaction), "reference": {
        "clip": str(clip), "subtitle": str(subtitle),
        "spans": [{"clip_ms": 1000, "reaction_ms": 2000, "length_ms": 1000}],
    }}
    result = invoke_worker(context, "desktop.backend.worker.programme_tools", payload)
    assert result == {"duration_ms": 4000, "count": 1, "sample": [
        {"start_ms": 2000, "end_ms": 3000, "text": "节目台词"},
    ]}


def test_exports_translation_and_preserves_all_uncertain_cues(tmp_path):
    output = tmp_path / "final.srt"
    output.write_text("intact", encoding="utf-8")
    texts = ["主播译文", "节目译文", "低置信", "重叠", "未分组"]
    (tmp_path / "final-translated.srt").write_text("\n\n".join(
        f"{i}\n00:00:{i:02},000 --> 00:00:{i:02},500\n{text}"
        for i, text in enumerate(texts, 1)), encoding="utf-8")
    annotated = tmp_path / "final-annotated.csv"
    annotation = "\n".join(
        f"sub|{i}|0.5||original|{text}|high|1|{label}|"
        for i, (text, label) in enumerate(zip(texts, ["s1", "s2", "s1?", "s1+s2", "s3"]), 1)
    )
    annotated.write_text(annotation, encoding="utf-8")
    rows = translated_rows(output)
    assert [track["track"] for track in describe_roles(rows)] == ["s1", "s2", "s3"]
    result = export_roles(output, rows, {"s1": "host", "s2": "programme"})
    folder = Path(result["directory"])
    assert result["counts"] == {"host": 1, "programme": 1, "review": 3}
    assert [row.text for row in parse_srt((folder / "review.srt").read_text(encoding="utf-8"))] == texts[2:]
    assert parse_srt((folder / "host.srt").read_text(encoding="utf-8"))[0].text == texts[0]
    assert output.read_text(encoding="utf-8") == "intact"
    annotated.write_text(annotation.replace(texts[0], "mismatch"), encoding="utf-8")
    with pytest.raises(ValueError, match="records do not match"):
        translated_rows(output)
