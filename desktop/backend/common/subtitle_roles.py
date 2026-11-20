"""Manual role exports from matched translation and annotation artifacts."""
from __future__ import annotations

from pathlib import Path
import re
import tempfile

_TRACK = re.compile(r"s[0-9]{1,6}")
_ROLES = ("host", "programme", "review")


def translated_rows(output: Path):
    from finesub.llm.output_protocol import decode_text_cell, split_annotated_row
    from finesub.subtitles.model import parse_srt

    translated = output.with_name(f"{output.stem}-translated.srt")
    annotated = output.with_name(f"{output.stem}-annotated.csv")

    def read(path):
        if path.is_symlink():
            raise ValueError("仅能使用任务生成的文件 / Only task-owned files are allowed")
        try:
            with path.open("rb") as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError("字幕文件过大 / Subtitle artifact too large")
            return raw.decode("utf-8-sig")
        except (OSError, UnicodeError) as error:
            raise ValueError("找不到保留的翻译字幕或说话人记录 / Translation or speaker metadata unavailable") from error

    subtitles = parse_srt(read(translated))
    annotation = [split_annotated_row(row) for row in read(annotated).splitlines()
                  if row.strip() and not row.lstrip().startswith("#")]
    if not subtitles or len(subtitles) != len(annotation):
        raise ValueError("字幕条数和说话人记录不一致 / Subtitle and speaker rows differ")
    result = []
    for cue, row in zip(subtitles, annotation):
        if row is None or "".join(cue.text.split()) != "".join(decode_text_cell(row.translation).split()):
            raise ValueError("字幕和说话人记录不匹配，无法安全分组 / Translation and speaker records do not match")
        label = row.spk.strip()
        result.append((cue, label if _TRACK.fullmatch(label) else ""))
    return result


def describe_roles(rows):
    tracks: dict[str, dict] = {}
    for cue, track in rows:
        if track:
            value = tracks.setdefault(track, {"track": track, "count": 0, "sample_ms": round(cue.start * 1000),
                                              "sample": cue.text[:160]})
            value["count"] += 1
    return sorted(tracks.values(), key=lambda row: (-row["count"], row["track"]))


def export_roles(output: Path, rows, assignment: dict[str, str]):
    from finesub.subtitles.model import render_srt

    available = {track for _, track in rows if track}
    if not assignment or len(assignment) > 100 or any(
        key not in available or role not in ("host", "programme") for key, role in assignment.items()
    ):
        raise ValueError("请先指定已确认的轨号 / Assign confirmed speaker tracks first")
    buckets = {role: [] for role in _ROLES}
    for cue, track in rows:
        buckets[assignment.get(track, "review")].append(cue)
    directory = Path(tempfile.mkdtemp(prefix="role-subtitles-", dir=output.parent))
    for role, cues in buckets.items():
        if cues:
            with (directory / f"{role}.srt").open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(render_srt(cues))
    return {"directory": str(directory), "counts": {role: len(cues) for role, cues in buckets.items()}}
