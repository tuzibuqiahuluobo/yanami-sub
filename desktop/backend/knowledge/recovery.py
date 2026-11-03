"""Verified restore copies; activation excludes every cooperating task starter."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from desktop.backend.knowledge.backup import (
    _digest, _inventory, _not_link, _SQLITE_FILES, create_backup, database_version,
    read_database, restore_backup, verify_backup,
)
from finesub_bootstrap.locks import holding_activity_barrier, holding_lock


def identity(root: Path, *, allow_unreadable: bool = False) -> str:
    skip = _SQLITE_FILES
    try:
        with closing(read_database(root / "knowledge.sqlite")) as source, closing(sqlite3.connect(":memory:")) as snapshot:
            source.backup(snapshot)
            digest = hashlib.sha256(snapshot.serialize())
    except (sqlite3.DatabaseError, FileNotFoundError):
        if not allow_unreadable:
            raise
        digest = hashlib.sha256(b"unreadable-store\0")
        skip = frozenset()
    files, _ = _inventory(root, skip=skip)
    for name, path in sorted(files.items()):
        digest.update((name + "\0" + _digest(path)).encode("utf-8"))
    return digest.hexdigest()


def backup_path(root: Path, identifier: str) -> Path:
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,240}", identifier) or identifier in {".", ".."}:
        raise ValueError("Invalid backup id")
    parent = root.parent / "knowledge-backups"
    _not_link(parent)
    path = parent / identifier
    _not_link(path)
    if path.resolve().parent != parent.resolve():
        raise ValueError("Backup escaped its owned directory")
    return path


def pending_path(root: Path) -> Path:
    return root.parent / f"{root.name}-recovery-pending.json"


def recover_interrupted(root: Path, coordination_root: Path) -> dict:
    pending = pending_path(root)
    with holding_activity_barrier(coordination_root, timeout=0), holding_lock(root.with_name(root.name + ".lock"), timeout=0):
        if not pending.exists():
            return {"recovered": False}
        _not_link(pending)
        marker = json.loads(pending.read_text(encoding="utf-8"))
        token = marker.get("token", "")
        if not re.fullmatch(r"[0-9a-f]{32}", token) or marker.get("knowledge_root") != str(root):
            raise ValueError("Invalid interrupted restore marker")
        directory = root.parent / "knowledge-restores" / token
        _not_link(directory.parent); _not_link(directory)
        receipt = json.loads((directory / "activation.json").read_text(encoding="utf-8"))
        previous = directory / "previous"
        if not root.exists():
            _not_link(previous); _not_link(previous / "knowledge")
            os.replace(previous / "knowledge", root)
            proposals = root.parent / "knowledge-proposals"
            if (previous / "knowledge-proposals").exists() and not proposals.exists():
                _not_link(previous / "knowledge-proposals")
                os.replace(previous / "knowledge-proposals", proposals)
        else:
            current = identity(root, allow_unreadable=True)
            if current not in {receipt["original_identity"], receipt["prepared_identity"]}:
                raise ValueError(f"知识库已变化，请人工核查，未覆盖任何文件 / Inspect restore at {directory}; no files overwritten")
        pending.unlink()
    return {"recovered": True, "note": "未完成的恢复已安全收尾，原数据仍保留 / Interrupted restore safely settled; original data retained."}


def list_backups(root: Path) -> dict:
    parent = root.parent / "knowledge-backups"
    if not parent.exists():
        return {"backups": []}
    _not_link(parent)
    rows = []
    for path in sorted(parent.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)[:100]:
        try:
            path = backup_path(root, path.name)
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            if Path(manifest["knowledge_source"]).resolve() != root:
                continue
            rows.append({"id": path.name, "created_at": manifest["created_at"],
                "schema_version": manifest["schema_version"], "files": len(manifest["files"])})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {"backups": rows}


def prepare(root: Path, identifier: str) -> dict:
    from desktop.backend.knowledge.schema_guard import prepare_knowledge_store
    from finesub.llm.knowledge.base import knowledge_write_lock
    from finesub.llm.knowledge.node.repo import KnowledgeRepo

    source = backup_path(root, identifier)
    manifest = verify_backup(source)
    if Path(manifest["knowledge_source"]).resolve() != root:
        raise ValueError("Backup belongs to another knowledge store")
    with knowledge_write_lock(root) as locked:
        if not locked:
            raise ValueError("Knowledge is busy")
        original = identity(root, allow_unreadable=True)
    token = uuid.uuid4().hex
    parent = root.parent / "knowledge-restores"
    parent.mkdir(exist_ok=True)
    _not_link(parent)
    destination = parent / token
    restore_backup(source, destination)
    staged = destination / "knowledge"
    prepare_knowledge_store(staged, config_files={})
    repo = KnowledgeRepo.open(staged)
    receipt = {"token": token, "knowledge_root": str(root), "backup": identifier,
        "original_identity": original, "prepared_identity": identity(staged), "revision": repo.rev}
    with (destination / "activation.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, ensure_ascii=False)
        stream.flush(); os.fsync(stream.fileno())
    return {"token": token, "backup": identifier, "revision": repo.rev,
        "path": str(destination), "entries": len(repo.subjects()),
        "note": "已校验并准备新副本；尚未启用，配置与密钥不会恢复 / Verified copy prepared; not active. Configuration and keys are not restored."}


def activate(root: Path, token: str, coordination_root: Path) -> dict:
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("Invalid restore token")
    directory = root.parent / "knowledge-restores" / token
    _not_link(directory.parent); _not_link(directory)
    receipt = json.loads((directory / "activation.json").read_text(encoding="utf-8"))
    if receipt.get("token") != token or receipt.get("knowledge_root") != str(root):
        raise ValueError("Restore identity mismatch")
    staged, previous = directory / "knowledge", directory / "previous"
    proposals = root.parent / "knowledge-proposals"
    with holding_activity_barrier(coordination_root, timeout=0), holding_lock(root.with_name(root.name + ".lock"), timeout=0):
        if pending_path(root).exists():
            raise ValueError("请先修复未完成的恢复 / Settle the interrupted restore first")
        _not_link(root)
        if not staged.exists() and previous.is_dir() and identity(root) == receipt["prepared_identity"]:
            return {"activated": True, "already_applied": True, "previous": str(previous), "revision": receipt["revision"]}
        _not_link(staged)
        if identity(root, allow_unreadable=True) != receipt["original_identity"] or identity(staged) != receipt["prepared_identity"]:
            raise ValueError("知识库或恢复副本已变化，请重新准备 / Knowledge changed; prepare again")
        for path in (root, staged, previous, proposals):
            if not path.resolve().is_relative_to(root.parent.resolve()):
                raise ValueError("Restore target escaped the data directory")
        rollback = None
        try:
            with closing(read_database(root / "knowledge.sqlite")) as source:
                version = database_version(source)
                rollback = create_backup(root, source, version, version)
        except (sqlite3.DatabaseError, FileNotFoundError):
            pass  # A damaged current DB is still preserved byte-for-byte below.
        previous.mkdir(exist_ok=False)
        marker = pending_path(root)
        with marker.open("x", encoding="utf-8") as stream:
            json.dump({"token": token, "knowledge_root": str(root)}, stream)
            stream.flush(); os.fsync(stream.fileno())
        moved_proposals = False
        try:
            os.replace(root, previous / "knowledge")
            if proposals.exists():
                _not_link(proposals)
                os.replace(proposals, previous / "knowledge-proposals")
                moved_proposals = True
            os.replace(staged, root)
        except BaseException:
            if moved_proposals:
                os.replace(previous / "knowledge-proposals", proposals)
            if (previous / "knowledge").exists() and not root.exists():
                os.replace(previous / "knowledge", root)
            marker.unlink()
            raise
        marker.unlink()
    return {"activated": True, "rollback_backup": str(rollback.parent.parent) if rollback else "",
        "previous": str(previous), "revision": receipt["revision"],
        "note": "知识库已启用；旧提案已隔离保留，请重新生成。未改配置或密钥 / Knowledge restored; old proposals retained separately. Regenerate proposals. Configuration and keys unchanged."}
