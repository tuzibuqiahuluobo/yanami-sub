"""User-triggered, bounded local diagnostic copies. Never uploads anything."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import platform
import re
import stat
from urllib.parse import urlencode
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

ISSUES_URL = "https://github.com/tuzibuqiahuluobo/yanami-sub/issues/new"
MAX_LOG_BYTES = 512 * 1024
MAX_FILES = 30
MAX_TOTAL_BYTES = 16 * 1024 * 1024


def safe_path(root: Path, relative: str) -> Path:
    """Reject traversal, links/junctions and alternate streams at every level."""
    if not relative or relative in {".", ".."} or "\\" in relative or ":" in relative:
        raise ValueError("Invalid log selection")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Invalid log selection")
    current = root
    for part in ("", *parts):
        if part:
            current = current / part
        metadata = current.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise ValueError("Log path contains a reparse point")
    if not current.resolve().is_relative_to(root.resolve()):
        raise ValueError("Log path escaped its directory")
    return current


def log_catalog(tasks: Path) -> list[dict]:
    rows = []
    if not tasks.is_dir() or tasks.is_symlink():
        return rows
    # Direct task directories plus the existing one-level batches container.
    folders = list(tasks.iterdir())
    batches = tasks / "batches"
    if batches in folders:
        folders.remove(batches)
        try:
            safe_path(tasks, "batches")
            folders.extend(batches.iterdir())
        except (OSError, ValueError):
            pass
    for folder in folders:
        relative = folder.relative_to(tasks).as_posix()
        try:
            safe = safe_path(tasks, relative)
            if not safe.is_dir():
                continue
            log = next((name for name in ("task-log.txt.part", "task-log.txt", "batch-log.txt")
                        if (safe / name).is_file() and not (safe / name).is_symlink()), "")
            modified = safe.stat().st_mtime
            if log:
                safe_path(tasks, relative + "/" + log)
                modified = (safe / log).stat().st_mtime
            rows.append({"id": relative, "name": folder.name, "path": str(safe),
                         "log_path": str(safe / log) if log else "",
                         "modified": modified, "batch": relative.startswith("batches/")})
        except (OSError, ValueError):
            continue
    return sorted(rows, key=lambda row: row["modified"], reverse=True)


def redact(text: str, secrets: list[str], private_roots: list[Path]) -> str:
    # Values include numeric keys: no provider-prefix assumptions.
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    for root in sorted(private_roots, key=lambda value: len(str(value)), reverse=True):
        for value in (str(root), str(root).replace("\\", "/")):
            text = re.sub(re.escape(value), "[LOCAL_PATH]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)(authorization|cookie|set-cookie)\s*[:=][^\r\n]+", r"\1: [REDACTED]", text)
    text = re.sub(r"(?i)((?:api[_-]?key|access[_-]?token|hf_token|github_token|password|secret)\s*[=:]\s*)[^\s,;]+",
                  r"\1[REDACTED]", text)
    text = re.sub(r"(?i)([?&](?:key|token|api_key|access_token|signature)=)[^&#\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)(https?|socks5h?)://[^/\s:@]+:[^@\s]+@", r"\1://[REDACTED]@", text)
    text = re.sub(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s]+", "[USER_HOME]", text)
    text = re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,})", "[REDACTED]", text)
    return text


def collect_diagnostics(*, tasks: Path, logs: Path, updates: Path, destination: Path,
                        selected: list[str], version: str, secrets: list[str],
                        private_roots: list[Path]) -> dict:
    if len(selected) > MAX_FILES or not all(isinstance(item, str) for item in selected):
        raise ValueError("Select at most 30 task/batch logs")
    catalog = {row["id"]: row for row in log_catalog(tasks)}
    candidates: list[tuple[str, Path, str]] = []
    notes = []
    for index, identifier in enumerate(dict.fromkeys(selected)):
        row = catalog.get(identifier)
        if row is None:
            raise ValueError("Task log selection no longer exists; refresh the list")
        if not row["log_path"]:
            notes.append(f"task {index + 1}: log not created")
        else:
            relative = Path(row["log_path"]).relative_to(tasks).as_posix()
            candidates.append((f"tasks/{index + 1}.txt", tasks, relative))
    # Known logs only. Never include configs, credentials, capsules or requests.
    for group, root, patterns in (("application", logs, ("session-*.log", "install-*.log", "*.install.log")),
                                   ("updates", updates, ("*.error.txt", "*.log"))):
        if not root.is_dir() or root.is_symlink():
            notes.append(f"{group}: directory unavailable")
            continue
        files = {}
        try:
            for pattern in patterns:
                for file in root.glob(pattern):
                    try:
                        if file.is_file():
                            files[file] = file.stat().st_mtime
                    except OSError:
                        notes.append(f"{group}: a log is inaccessible")
        except OSError:
            notes.append(f"{group}: cannot enumerate logs")
        for index, file in enumerate(sorted(files, key=files.get, reverse=True)[:10]):
            candidates.append((f"{group}/{index + 1}.txt", root, file.name))
    contents: list[tuple[str, bytes]] = []
    size = 0
    seen = set()
    for label, root, relative in candidates[:MAX_FILES]:
        try:
            source = safe_path(root, relative)
            if source.resolve() in seen:
                continue
            seen.add(source.resolve())
            with source.open("rb") as handle:
                handle.seek(0, 2)
                original_size = handle.tell()
                handle.seek(max(0, original_size - MAX_LOG_BYTES))
                raw = handle.read(MAX_LOG_BYTES)
            text = raw.decode("utf-8-sig", errors="replace")
            if original_size > len(raw):
                text = "[TRUNCATED: latest 512 KiB snapshot]\n" + text
            encoded = redact(text, secrets, private_roots).encode("utf-8")
            if size + len(encoded) > MAX_TOTAL_BYTES:
                notes.append(f"{label}: omitted by total size limit")
                continue
            contents.append((label, encoded))
            size += len(encoded)
        except (OSError, ValueError) as error:
            notes.append(f"{label}: unavailable ({type(error).__name__})")
    report = ("# Yanami Sub diagnostic snapshot\n\n"
              f"Version: {version}\nCaptured: {datetime.now(timezone.utc).isoformat()}\n"
              f"OS: {platform.system()} {platform.release()}\nPython: {platform.python_version()}\n"
              "Logs are bounded snapshots, not final transcripts. No media, subtitles, configs or Agent sessions included.\n"
              "Review all files before attaching to a PUBLIC GitHub Issue. Redaction cannot detect every free-text secret.\n\n"
              "## Included\n" + "\n".join(f"- {label} ({len(data)} bytes)" for label, data in contents)
              + "\n\n## Missing / limits\n" + "\n".join(notes or ["None"]))
    destination.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.resolve() != destination.absolute():
        raise ValueError("Diagnostic destination must not be a link")
    output = destination / ("diagnostics-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".zip")
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        archive.writestr("report.md", report.encode("utf-8"))
        for label, data in contents:
            archive.writestr(label, data)
    return {"path": str(output), "report": report, "files": len(contents), "size": output.stat().st_size}


def issue_url(title: str, description: str, version: str) -> str:
    # Keep the URL small; raw logs never belong in a URL.
    body = f"Yanami Sub {version}\n\n{description[:500]}\n\n请附重现步骤、预期结果，以及检查后的日志/截图。"
    return ISSUES_URL + "?" + urlencode({"title": title[:100], "body": body})
