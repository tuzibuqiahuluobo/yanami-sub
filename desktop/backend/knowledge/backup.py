"""Local migration snapshots; restore only into a new, inactive directory."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import time
from typing import Mapping
import uuid


_DATABASE = "knowledge.sqlite"
_SQLITE_FILES = {_DATABASE, *(_DATABASE + suffix for suffix in ("-wal", "-shm", "-journal"))}
_CONFIG_FILES = {"config.toml", "model_catalog.psv"}
_FORMAT = 1


def config_sources() -> dict[str, Path]:
    from finesub.paths import resolve_config_file, resolve_model_catalog_override

    return {name: path for name, path in (
        ("config.toml", resolve_config_file()),
        ("model_catalog.psv", resolve_model_catalog_override()),
    ) if path is not None}


def database_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    if row is None or not str(row[0]).isdigit():
        raise ValueError("知识库缺少有效的版本信息 / Invalid knowledge schema version")
    return int(row[0])


def read_database(database: Path) -> sqlite3.Connection:
    _not_link(database)
    return sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)


def _check_time(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError("知识库备份超时，已停止升级 / Knowledge backup timed out")


def _not_link(path: Path) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"备份不跟随链接或重解析点 / Snapshot refuses links: {path}")
    return info


def _inventory(root: Path, *, skip: set[str] = frozenset()) -> tuple[dict[str, Path], set[str]]:
    if not stat.S_ISDIR(_not_link(root).st_mode):
        raise ValueError(f"Not a snapshot directory: {root}")
    files, directories = {}, set()
    def on_error(error):
        raise error
    for directory, children, names in os.walk(root, followlinks=False, onerror=on_error):
        base = Path(directory)
        for name in children:
            child = base / name
            if not stat.S_ISDIR(_not_link(child).st_mode):
                raise ValueError(f"Not a regular directory: {child}")
            directories.add(child.relative_to(root).as_posix())
        for name in names:
            path = base / name
            relative = path.relative_to(root).as_posix()
            if relative in skip:
                continue
            if not stat.S_ISREG(_not_link(path).st_mode):
                raise ValueError(f"Not a regular snapshot file: {path}")
            files[relative] = path
    return files, directories


def _digest(path: Path, deadline: float = float("inf")) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            _check_time(deadline)
            digest.update(chunk)
    return digest.hexdigest()


def _copy(source: Path, destination: Path, deadline: float = float("inf")) -> None:
    if not stat.S_ISREG(_not_link(source).st_mode):
        raise ValueError(f"Not a regular snapshot file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        while chunk := reader.read(1024 * 1024):
            _check_time(deadline)
            writer.write(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    shutil.copystat(source, destination)


def _sources(root: Path, configs: Mapping[str, Path]) -> tuple[dict[str, Path], set[str]]:
    files, directories = {}, {"knowledge"}
    for label, source, skip in (
        ("knowledge", root, _SQLITE_FILES),
        ("knowledge-proposals", root.parent / "knowledge-proposals", frozenset()),
    ):
        try:
            _not_link(source)
        except FileNotFoundError:
            continue
        entries, dirs = _inventory(source, skip=skip)
        files.update({f"{label}/{name}": path for name, path in entries.items()})
        directories.update({label, *(f"{label}/{name}" for name in dirs)})
    for name, path in configs.items():
        if name not in _CONFIG_FILES:
            raise ValueError(f"Unknown migration config file: {name}")
        if not stat.S_ISREG(_not_link(path).st_mode):
            raise ValueError(f"Not a regular config file: {path}")
        files[f"config/{name}"] = path
        directories.add("config")
    return files, directories


def _snapshot_database(source: sqlite3.Connection, destination: Path, stored: int, deadline: float) -> None:
    temporary = destination.with_suffix(".sqlite.tmp")
    with closing(sqlite3.connect(temporary)) as connection:
        source.backup(connection, pages=256, progress=lambda *_: _check_time(deadline))
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RuntimeError("知识库备份校验失败，已停止升级 / Invalid knowledge backup")
        if database_version(connection) != stored:
            raise RuntimeError("备份期间知识库版本发生变化，已停止升级")
    with temporary.open("r+b") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def create_backup(root: Path, source: sqlite3.Connection, stored: int, target: int, *,
                  config_files: Mapping[str, Path] | None = None, timeout: float = 30) -> Path:
    """Caller holds the core knowledge write lock through backup AND migration."""
    configs = config_sources() if config_files is None else dict(config_files)
    files, directories = _sources(root, configs)
    timestamps = {name: path.stat().st_mtime_ns for name, path in files.items()}
    backups = root.parent / "knowledge-backups"
    backups.mkdir(parents=True, exist_ok=True)
    _not_link(backups)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = backups / f"{root.name}-schema-{stored}-before-{target}-{stamp}-{uuid.uuid4().hex}"
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=backups) as temporary:
        stage = Path(temporary)
        for name in sorted(directories):
            (stage / name).mkdir(parents=True, exist_ok=True)
        _snapshot_database(source, stage / "knowledge" / _DATABASE, stored, deadline)
        for name, path in files.items():
            _copy(path, stage / name, deadline)
        after_files, after_dirs = _sources(root, configs)
        if after_files != files or after_dirs != directories or any(
            path.stat().st_mtime_ns != timestamps[name] or
            _digest(path, deadline) != _digest(stage / name, deadline) for name, path in files.items()
        ):
            raise RuntimeError("备份期间用户文件已变化，已停止升级 / Migration data changed during backup")
        entries, _ = _inventory(stage)
        manifest = {
            "format": _FORMAT, "schema_version": stored, "target_schema": target,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "knowledge_source": str(root),
            "config_sources": {name: str(path) for name, path in configs.items()},
            "directories": sorted(directories),
            "files": {name: {"size": path.stat().st_size, "sha256": _digest(path, deadline)}
                      for name, path in sorted(entries.items())},
        }
        with (stage / "manifest.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        verify_backup(stage)
        _check_time(deadline)
        os.replace(stage, final)
    return final / "knowledge" / _DATABASE


def _bundle(path: Path) -> Path:
    path = path.expanduser().resolve()
    return path.parent.parent if path.name == _DATABASE and path.parent.name == "knowledge" else path


def _relative(name: str) -> None:
    if not isinstance(name, str):
        raise ValueError("Invalid snapshot path")
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or path.as_posix() != name or
        path.parts[0] not in {"knowledge", "knowledge-proposals", "config"} or
        any(part in {".", ".."} or part[-1:] in {".", " "} or
            any(char in part for char in '\\:*?"<>|') or any(ord(char) < 32 for char in part) or
            re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
            for part in path.parts)):
        raise ValueError(f"Invalid snapshot path: {name}")


def verify_backup(path: Path) -> dict:
    root = _bundle(path)
    files, directories = _inventory(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("format") != _FORMAT:
        raise ValueError("Unsupported migration snapshot")
    if not isinstance(manifest.get("knowledge_source"), str) or not Path(manifest["knowledge_source"]).is_absolute():
        raise ValueError("Invalid snapshot source metadata")
    entries, recorded_dirs = manifest.get("files"), manifest.get("directories")
    if not isinstance(entries, dict) or not isinstance(recorded_dirs, list) or "knowledge/knowledge.sqlite" not in entries:
        raise ValueError("Invalid migration snapshot manifest")
    names = [*entries, *recorded_dirs]
    for name in names:
        _relative(name)
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("Duplicate snapshot paths")
    if set(files) != {*entries, "manifest.json"} or directories != set(recorded_dirs):
        raise ValueError("Snapshot file list changed")
    for name, record in entries.items():
        if (not isinstance(record, dict) or not isinstance(record.get("size"), int) or
            not isinstance(record.get("sha256"), str) or
            files[name].stat().st_size != record["size"] or _digest(files[name]) != record["sha256"]):
            raise ValueError(f"Snapshot checksum mismatch: {name}")
    database = root / "knowledge" / _DATABASE
    # Only verified standalone copies are immutable; live readers must include WAL.
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
        if (connection.execute("PRAGMA quick_check").fetchall() != [("ok",)] or
            database_version(connection) != manifest.get("schema_version")):
            raise ValueError("Invalid snapshot database")
    return manifest


def restore_backup(path: Path, destination: Path) -> Path:
    """Never overwrite or activate a live store, even when an old core is absent."""
    manifest = verify_backup(path)
    source = _bundle(path)
    destination = destination.expanduser().absolute()
    original = Path(manifest["knowledge_source"]).resolve()
    if destination.resolve().is_relative_to(source) or destination.resolve().is_relative_to(original):
        raise ValueError("Restore destination must be outside the snapshot and live knowledge directory")
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    # Publish the manifest last. An interrupted copy is not a verified restore;
    # its new directory is kept for inspection, never copied over live data.
    for name in manifest["directories"]:
        (destination / name).mkdir(parents=True, exist_ok=True)
    for name in manifest["files"]:
        _copy(source / name, destination / name)
    _copy(source / "manifest.json", destination / "manifest.json")
    verify_backup(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a private migration backup or restore it into a NEW directory; never activates it.")
    parser.add_argument("action", choices=("verify", "restore"))
    parser.add_argument("backup", type=Path)
    parser.add_argument("--to", type=Path, dest="destination")
    args = parser.parse_args()
    if args.action == "restore":
        if args.destination is None:
            parser.error("restore requires --to NEW_DIRECTORY")
        result = restore_backup(args.backup, args.destination)
        print(f"Verified restore copy (not activated): {result}")
    else:
        manifest = verify_backup(args.backup)
        print(f"Verified private snapshot: schema={manifest['schema_version']}; files={len(manifest['files'])}")


if __name__ == "__main__":
    main()
