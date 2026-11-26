"""Prepare public issue text locally and publish only an explicitly reviewed draft."""
from __future__ import annotations

import base64
import binascii
from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zipfile import ZipFile

from PIL import Image, ImageOps


REPOSITORY = "github.com/tuzibuqiahuluobo/yanami-sub"
MAX_INPUT = 2 * 1024 * 1024
MAX_ATTACHMENTS = 5
_ISSUE_LINK = re.compile(r"https://github\.com/tuzibuqiahuluobo/yanami-sub/issues/\d+")
_ERROR = re.compile(r"\b(?:\w*(?:Error|Exception)|Traceback)\b|失败|报错|超时", re.IGNORECASE)


def attachment_files(attachments: list) -> list[tuple[str, bytes]]:
    if not isinstance(attachments, list) or len(attachments) > MAX_ATTACHMENTS:
        raise ValueError("最多选择 5 个截图或日志 / Select up to 5 screenshots or logs")
    result = []
    for index, row in enumerate(attachments, 1):
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not isinstance(row.get("data"), str):
            raise ValueError("Invalid attachment")
        ext = Path(row["name"]).suffix.lower()
        try:
            if len(row["data"]) > ((MAX_INPUT + 2) // 3) * 4:
                raise ValueError
            raw = base64.b64decode(row["data"], validate=True)
            if not raw or len(raw) > MAX_INPUT:
                raise ValueError
        except (ValueError, binascii.Error):
            raise ValueError("附件为空、无法读取或超过 2 MiB / Attachment is empty, invalid or over 2 MiB") from None
        if ext in {".png", ".jpg", ".jpeg", ".webp"}:
            try:
                with Image.open(BytesIO(raw), formats=("PNG", "JPEG", "WEBP")) as image:
                    if image.width * image.height > 16_000_000:
                        raise ValueError
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((1600, 1600))
                    rgb = image.convert("RGB")
                    rgb.info.clear()
                    output = BytesIO()
                    rgb.save(output, format="JPEG", quality=88)
                result.append((f"screenshots/{index}.jpg", output.getvalue()))
            except (OSError, ValueError, Image.DecompressionBombError):
                raise ValueError("无法读取截图或分辨率过大 / Screenshot is unreadable or too large") from None
        elif ext in {".log", ".txt"}:
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                raw = raw.decode("utf-16", errors="replace").encode("utf-8")
            if b"\0" in raw:
                raise ValueError("只支持文本日志 / Only text logs are supported")
            result.append((f"attached-logs/{index}.txt", raw[-512 * 1024:]))
        else:
            raise ValueError("只支持 PNG、JPEG、WebP 截图和 TXT、LOG 日志 / Unsupported attachment type")
    return result


def issue_draft(fields: dict, *, version: str, system: str, contents: list[tuple[str, bytes]], clean) -> tuple[str, str]:
    if not isinstance(fields, dict) or any(not isinstance(fields.get(key, ""), str) for key in ("title", "steps", "expected", "actual")):
        raise ValueError("Invalid issue fields")
    en = fields.get("language") == "en"
    labels = ("Steps to reproduce", "Expected result", "Actual result", "Environment", "Diagnostic excerpts") if en else (
        "重现步骤", "预期结果", "实际结果", "运行环境", "诊断摘要")
    missing = "Not provided" if en else "未填写"
    def plain(value: str, limit: int) -> str:
        return clean(value.strip()[:limit])

    excerpts = []
    for name, data in contents:
        if name.endswith(".txt") and not name.startswith(("application/", "updates/")):
            recent = data.decode("utf-8", errors="replace").splitlines()[-300:]
            lines = [line.strip()[:220].replace("`", "'") for line in recent if _ERROR.search(line)]
            if name.startswith("attached-logs/") and not lines:
                lines = [line.strip()[:220].replace("`", "'") for line in recent if line.strip()][-1:]
            excerpts.extend(line for line in lines[-2:] if line not in excerpts)
    title = plain(fields.get("title", ""), 100).replace("\n", " ").replace("\r", " ")
    actual = plain(fields.get("actual", ""), 6000)
    if not title:
        # Take the user's first sentence, never a log line that might expose identifiers.
        title = re.split(r"[\n。！？]", actual, 1)[0][:75] or ("Yanami Sub problem" if en else "Yanami Sub 问题反馈")
    sections = [
        f"## {label}\n\n{plain(fields.get(key, ''), 4000) or missing}"
        for label, key in zip(labels[:2], ("steps", "expected"), strict=True)
    ]
    sections += [f"## {labels[2]}\n\n{actual or missing}", f"## {labels[3]}\n\n- Yanami Sub: {version}\n- OS: {system}"]
    snippets = "\n".join(excerpts[-8:])
    if snippets:
        sections.append(f"## {labels[4]}\n\n```text\n{snippets}\n```")
    return title, "\n\n".join(sections) + "\n"


def _cli_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_DEBUG", "DEBUG"):
        env.pop(key, None)
    env.update(GH_HOST="github.com", GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
    return env


def _gh(executable: str, args: list[str], *, cwd: Path, timeout: int):
    return subprocess.run([executable, *args], cwd=cwd, env=_cli_env(), capture_output=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def cli_capability(cwd: Path) -> str:
    executable = shutil.which("gh")
    if not executable:
        return "missing"
    try:
        help_result = _gh(executable, ["issue", "create", "--help"], cwd=cwd, timeout=5)
        status = _gh(executable, ["auth", "status", "--hostname", "github.com"], cwd=cwd, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return "missing"
    if status.returncode:
        return "signed_out"
    return "screenshots" if "--attach" in help_result.stdout else "text"


def publish_issue(title: str, body: str, directory: Path, package: bytes, screenshots: list[str]) -> dict:
    executable = shutil.which("gh")
    mode = cli_capability(directory)
    if not executable or mode not in {"text", "screenshots"} or (screenshots and mode != "screenshots"):
        raise ValueError("GitHub CLI 未登录或不支持所选附件，请使用浏览器 / GitHub CLI login or attachment support unavailable; use the browser")
    try:
        with tempfile.TemporaryDirectory(prefix="issue-", dir=directory) as temporary:
            root = Path(temporary)
            (root / "issue.md").write_text(body, encoding="utf-8")
            args = ["issue", "create", "--repo", REPOSITORY, f"--title={title}", "--body-file", "issue.md"]
            with ZipFile(BytesIO(package)) as archive:
                for index, name in enumerate(screenshots, 1):
                    local = f"screenshot-{index}.jpg"
                    (root / local).write_bytes(archive.read(name))
                    args.extend(("--attach", local))
            completed = _gh(executable, args, cwd=root, timeout=90)
    except (OSError, subprocess.SubprocessError):
        raise ValueError("提交结果未知，请先查看仓库 Issues，再决定是否重试 / Result unknown; check repository Issues before retrying") from None
    url = next((line.strip() for line in completed.stdout.splitlines() if _ISSUE_LINK.fullmatch(line.strip())), "")
    if not url:
        raise ValueError("没有收到 Issue 地址。请先检查仓库，避免重复提交 / No issue URL received; check the repository before retrying")
    return {"url": url, "attachments_complete": completed.returncode == 0}
