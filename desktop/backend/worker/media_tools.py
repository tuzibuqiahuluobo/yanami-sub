"""Media metadata and downloads using the managed yt-dlp and FFmpeg."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from desktop.backend.common.models import LinkFormat

_LIMIT = 12 * 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_AUDIO_EXT = {"mp4": "m4a", "webm": "webm"}
_FORMAT_UNAVAILABLE = ("所选视频档位已不可用。请重新读取链接并选择档位，或点「恢复自动」后重试。"
                       " / The selected video format is unavailable. Refresh the link and select a format, or use automatic.")


def validate_url(url: str, *, youtube: bool = False) -> str:
    if not isinstance(url, str) or len(url) > 8192 or any(c.isspace() for c in url):
        raise ValueError("请输入有效的视频网址 / Enter a valid video URL")
    parts = urlsplit(url)
    if (parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username is not None or parts.password is not None
            or (youtube and parts.hostname not in _YT_HOSTS)):
        raise ValueError("请输入有效的 YouTube 视频链接 / Enter a YouTube video link"
                         if youtube else "请输入有效的视频网址 / Enter a valid video URL")
    return url


def downloader(**options):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as error:
        raise ValueError("请先在资源页安装 yt-dlp / Install yt-dlp in Resources") from error
    return YoutubeDL({"noplaylist": True, "socket_timeout": 12, **options})


def _extract(ydl, url):
    info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict) or info.get("_type") in {"playlist", "multi_video"}:
        raise ValueError("请选择单个视频链接 / Choose a single video link")
    return info


def video_formats(info):
    rows = info.get("formats") or []
    audio = {row.get("ext") for row in rows
             if not row.get("has_drm") and row.get("vcodec") == "none"
             and row.get("acodec") and row["acodec"] != "none"}
    distinct = {}
    for row in rows:
        fmt, ext, height, fps = (row.get(key) for key in ("format_id", "ext", "height", "fps"))
        if (not isinstance(fmt, str) or not _ID.fullmatch(fmt) or row.get("has_drm")
                or ext not in {"mp4", "webm", "mkv"} or not row.get("vcodec") or row["vcodec"] == "none"
                or not row.get("acodec")
                or not isinstance(height, int) or height <= 0):
            continue
        if row["acodec"] == "none" and (_AUDIO_EXT[ext] not in audio if ext in _AUDIO_EXT else not audio):
            continue
        fps = round(fps, 3) if isinstance(fps, (int, float)) and math.isfinite(fps) and fps > 0 else None
        distinct[ext, height, fps] = {"format_id": fmt, "container": ext, "height": height, "fps": fps}
    return sorted(distinct.values(), key=lambda row: (row["container"], -row["height"], -(row["fps"] or 0)))


def _subtitle_tracks(info):
    for group, automatic in (("subtitles", False), ("automatic_captions", True)):
        for language, entries in (info.get(group) or {}).items():
            by_ext = {
                entry["ext"]: entry["url"] for entry in entries
                if entry.get("ext") in {"vtt", "srt"} and isinstance(entry.get("url"), str)
                and urlsplit(entry["url"]).scheme == "https"
                and (not automatic or "tlang" not in parse_qs(urlsplit(entry["url"]).query))
            }
            if by_ext and language != "live_chat":
                label = next((row.get("name") for row in entries if row.get("name")), language)
                yield {"language": language, "label": label, "automatic": automatic}, by_ext


def inspect_link(url: str, *, captions: bool = False):
    url = validate_url(url, youtube=captions)
    with downloader(quiet=True, skip_download=True, extractor_retries=1) as ydl:
        info = _extract(ydl, url)
    return {"title": str(info.get("title") or "")[:250],
            "formats": [] if captions else video_formats(info),
            "tracks": [row for row, _ in _subtitle_tracks(info)] if captions else []}


def download_selected_video(url: str, choice: LinkFormat, task_dir: Path) -> Path:
    from finesub.media.ffmpeg import resolve_ffmpeg, resolve_ffprobe, run_capture
    from finesub.media.source import YTDLP_RETRY_OPTIONS, record_video_info, validate_video_audio_coverage
    from finesub.paths import resolve_reference_data_root

    url = validate_url(url)
    key = hashlib.sha256(json.dumps([url, choice.container, choice.format_id]).encode()).hexdigest()[:24]
    folder = task_dir / "link-media" / key
    if not folder.resolve().is_relative_to(task_dir.resolve()):
        raise ValueError("视频缓存路径不在任务目录内 / Video cache is outside the task directory")
    folder.mkdir(parents=True, exist_ok=True)
    video = folder / f"source.{choice.container}"
    if video.is_symlink() or (video.exists() and not video.is_file()):
        raise ValueError("视频缓存路径无效 / Invalid video cache path")
    title = None
    if not video.exists():
        # yt-dlp treats unquoted decimal filters as numbers; format IDs are strings.
        match = f'[format_id="{choice.format_id}"][ext={choice.container}][vcodec!=none]'
        audio = "ba" + (f"[ext={_AUDIO_EXT[choice.container]}]" if choice.container in _AUDIO_EXT else "")
        with downloader(**YTDLP_RETRY_OPTIONS, format=f"best{match}/bestvideo{match}+{audio}",
                        outtmpl=str(folder / "source.%(ext)s"), merge_output_format=choice.container,
                        ffmpeg_location=resolve_ffmpeg()) as ydl:
            from yt_dlp.utils import DownloadError

            try:
                info = ydl.extract_info(url, download=True)
                title = info.get("title") if isinstance(info, dict) else None
            except DownloadError as error:
                if "Requested format is not available" in str(error):
                    raise ValueError(_FORMAT_UNAVAILABLE) from error
                raise
    if not video.is_file():
        raise ValueError("未找到下载完成的视频文件，请重试 / The finished video file was not found; retry the download")
    result = run_capture([resolve_ffprobe(), "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(video)])
    tracks = {row.get("codec_type") for row in json.loads(result.stdout).get("streams", [])}
    if not {"audio", "video"} <= tracks:
        raise ValueError("下载结果缺少视频或音轨，请改用其他格式 / The download is missing a video or audio stream")
    validate_video_audio_coverage(video)
    if isinstance(title, str) and title.strip():
        try:
            record_video_info(url, title, resolve_reference_data_root())
        except (OSError, ValueError):
            pass  # Title metadata is optional; keep the usable download.
    return video


def save_subtitle(url: str, language: str, automatic: bool, extension: str, destination: str) -> dict:
    from finesub.media.ffmpeg import resolve_ffmpeg, run_capture
    from finesub.subtitles.model import parse_srt

    url = validate_url(url, youtube=True)
    target = Path(destination)
    if extension not in {"srt", "vtt", "txt"} or target.suffix.lower() != f".{extension}" or not target.is_absolute():
        raise ValueError("请选择匹配的字幕文件名 / Choose a filename that matches the subtitle format")
    if target.exists():
        raise ValueError("文件已存在，请选择新文件名 / File exists; choose another name")
    with downloader(quiet=True, skip_download=True, extractor_retries=1) as ydl:
        tracks = _subtitle_tracks(_extract(ydl, url))
        available = next((files for row, files in tracks if row["language"] == language and row["automatic"] == automatic), None)
        if not available:
            raise ValueError("字幕轨道已不可用，请重新读取 / The subtitle track is unavailable; refresh the list")
        wanted = "vtt" if extension == "vtt" else "srt"
        original = wanted if wanted in available else next(iter(available))
        with ydl.urlopen(available[original]) as response:
            raw = response.read(_LIMIT + 1)
    if not raw or len(raw) > _LIMIT:
        raise ValueError("字幕为空或超过 12 MiB / Subtitle is empty or exceeds 12 MiB")
    if original != wanted:
        with TemporaryDirectory(prefix="yanami-subs-") as dirname:
            incoming = Path(dirname) / f"track.{original}"
            incoming.write_bytes(raw)
            raw = run_capture([resolve_ffmpeg(), "-nostdin", "-v", "error", "-i", str(incoming),
                               "-f", "webvtt" if wanted == "vtt" else "srt", "-"]).stdout.encode("utf-8")
    if wanted == "srt":
        cues = parse_srt(raw.decode("utf-8-sig"))
        if not cues:
            raise ValueError("没有可保存的字幕行 / No subtitle cues to save")
        if extension == "txt":
            raw = ("\n".join(cue.text for cue in cues) + "\n").encode("utf-8")
    elif not raw.lstrip(b"\xef\xbb\xbf").startswith(b"WEBVTT"):
        raise ValueError("视频站点没有返回有效 VTT / The site did not return valid WebVTT")
    with target.open("xb") as file:
        file.write(raw)
    return {"path": str(target)}


def main() -> int:
    try:
        body = json.loads(sys.stdin.readline())
        if body["action"] == "inspect":
            data = inspect_link(body["url"], captions=body["captions"])
        elif body["action"] == "save":
            data = save_subtitle(body["url"], body["language"], body["automatic"], body["extension"], body["destination"])
        else:
            raise ValueError("Unknown media tool")
        result = {"ok": True, "data": data}
    except Exception as error:
        result = {"ok": False, "error": {"message": str(error)}}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
