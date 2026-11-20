"""Validate and place programme subtitles on a reaction video's timeline."""
from __future__ import annotations

import math
from pathlib import Path
import shutil
import subprocess
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, model_validator

LIMIT_MS = 24 * 60 * 60 * 1000 - 1
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v"}


class ReferenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    clip_ms: int = Field(ge=0, le=LIMIT_MS)
    reaction_ms: int = Field(ge=0, le=LIMIT_MS)
    length_ms: int = Field(gt=0, le=LIMIT_MS)


class ProgrammeReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    clip: str = Field(min_length=1, max_length=32768)
    subtitle: str = Field(min_length=1, max_length=32768)
    subtitle_offset_ms: int = Field(default=0, ge=0, le=LIMIT_MS)
    spans: list[ReferenceSpan] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def check_spans(self):
        last_end = 0
        for span in sorted(self.spans, key=lambda row: row.reaction_ms):
            if span.reaction_ms < last_end:
                raise ValueError("主播视频中的对齐区间不能重叠 / Reaction ranges must not overlap")
            last_end = span.reaction_ms + span.length_ms
            if last_end > LIMIT_MS or span.clip_ms + span.length_ms > LIMIT_MS:
                raise ValueError("对齐区间超出 24 小时 / Range exceeds 24 hours")
        return self


def _local_file(value: str, extensions: set[str], description: str) -> Path:
    try:
        path = Path(value).expanduser()
        if not path.is_absolute() or path.suffix.lower() not in extensions or not path.is_file():
            raise ValueError
        return path.resolve()
    except (OSError, ValueError) as error:
        raise ValueError(f"请选择可读取的本地{description} / Choose a readable local {description}") from error


def _video_duration_ms(path: Path, *, search_path: str | None) -> int:
    binary = shutil.which("ffprobe", path=search_path)
    if not binary:
        raise ValueError("请先在资源页安装 FFmpeg / Install FFmpeg in Resources first")
    try:
        result = subprocess.run(
            [binary, "-v", "error", "-protocol_whitelist", "file",
             "-format_whitelist", "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm",
             "-select_streams", "v:0", "-show_entries", "stream=index:format=duration",
             "-of", "json", str(path)],
            capture_output=True, encoding="utf-8", errors="replace", check=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        import json
        metadata = json.loads(result.stdout)
        seconds = float(metadata["format"]["duration"])
        if not metadata.get("streams") or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError
        return round(seconds * 1000)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        raise ValueError("无法读取视频时长，请确认文件能正常播放 / Could not read video duration") from error


def load_alignment(reference: ProgrammeReference, reaction: str, *, search_path: str | None = None):
    from finesub.subtitles.model import SrtSegment, parse_srt

    clip = _local_file(reference.clip, VIDEO_EXTENSIONS, "视频切片 / video clip")
    reaction_video = _local_file(reaction, VIDEO_EXTENSIONS, "主播视频 / reaction video")
    subtitle = _local_file(reference.subtitle, {".srt"}, "SRT 字幕 / SRT subtitle")
    try:
        with subtitle.open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("SRT 不得超过 2 MiB / SRT must not exceed 2 MiB")
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        source = parse_srt(raw.decode(encoding))
        if not 0 < len(source) <= 5000 or any(
            row.end <= row.start or not row.text.strip() or "\x00" in row.text for row in source
        ):
            raise ValueError("字幕必须包含 1–5000 条有效时间轴 / Expected 1–5000 valid cues")
    except (OSError, ValueError) as error:
        raise ValueError(f"节目字幕读取失败 / Unable to read programme SRT: {error}") from error
    duration_ms = _video_duration_ms(clip, search_path=search_path)
    reaction_ms = _video_duration_ms(reaction_video, search_path=search_path)
    aligned = []
    for index, span in enumerate(reference.spans, start=1):
        end = span.clip_ms + span.length_ms
        if end > duration_ms:
            raise ValueError(f"区间 {index} 超过切片时长 / Range {index} extends beyond the clip")
        if span.reaction_ms + span.length_ms > reaction_ms:
            raise ValueError(f"区间 {index} 超过主播视频时长 / Range {index} extends beyond the reaction video")
        for row in source:
            start_ms = max(round(row.start * 1000) - reference.subtitle_offset_ms, span.clip_ms)
            end_ms = min(round(row.end * 1000) - reference.subtitle_offset_ms, end)
            if start_ms >= end_ms:
                continue
            delta = span.reaction_ms - span.clip_ms
            aligned.append(SrtSegment(0, (start_ms + delta) / 1000, (end_ms + delta) / 1000, row.text))
            if len(aligned) > 5000:
                raise ValueError("对齐后字幕超过 5000 条，请缩短对齐范围 / Too many aligned cues")
    if not aligned:
        raise ValueError("没有字幕落在所选时间段，请检查 SRT 起点与对齐区间 / No cues matched the selected ranges")
    return sorted(aligned, key=lambda row: (row.start, row.end)), duration_ms


def quoted_text(text: str) -> str:
    """Keep subtitle data from forming prompt markup or control lines."""
    text = " ".join(text.split())
    text = "".join(c for c in text if unicodedata.category(c) not in {"Cc", "Cf"})
    return text[:240].translate(str.maketrans("<>|", "＜＞｜"))
