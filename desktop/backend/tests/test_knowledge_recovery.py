from contextlib import closing
import json
from pathlib import Path

import pytest
from finesub_bootstrap.locks import holding_activity, LockUnavailable
from finesub.llm.knowledge.node.repo import KnowledgeRepo
from finesub.llm.knowledge.node import schema

from desktop.backend.knowledge import backup, recovery
from desktop.backend.worker.knowledge_main import _dispatch


@pytest.fixture
def restore_point(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    monkeypatch.setattr(backup, "config_sources", lambda: {})
    _dispatch({"action": "maintenance", "command": "new", "args": ["common", "初音ミク", "--intro", "原版", "--type", "其他"]})
    KnowledgeRepo.forget(root)
    with closing(backup.read_database(root / "knowledge.sqlite")) as source:
        bundle = backup.create_backup(root, source, schema.SCHEMA_VERSION, schema.SCHEMA_VERSION).parent.parent
    _dispatch({"action": "maintenance", "command": "new", "args": ["common", "新条目", "--intro", "恢复前", "--type", "其他"]})
    KnowledgeRepo.forget(root)
    return root, bundle, tmp_path / "coordination"


def test_prepare_is_inactive_and_activation_preserves_current_and_quarantines_proposals(restore_point):
    root, bundle, coordination = restore_point
    config = root.parent / "config.toml"
    config.write_text("# current config", encoding="utf-8")
    proposals = root.parent / "knowledge-proposals"
    proposals.mkdir(); (proposals / "pending.json").write_text('{"pending":true}', encoding="utf-8")
    before = recovery.identity(root)
    assert recovery.list_backups(root)["backups"][0]["id"] == bundle.name
    prepared = recovery.prepare(root, bundle.name)
    KnowledgeRepo.forget()
    assert recovery.identity(root) == before and prepared["entries"] == 1
    result = recovery.activate(root, prepared["token"], coordination)
    assert result["activated"]
    assert config.read_text(encoding="utf-8") == "# current config"
    assert not proposals.exists()
    assert (root.parent / "knowledge-restores" / prepared["token"] / "previous" / "knowledge-proposals" / "pending.json").is_file()
    assert backup.verify_backup(Path(result["rollback_backup"]))
    assert recovery.activate(root, prepared["token"], coordination)["already_applied"]
    restored = KnowledgeRepo.open(root)
    assert restored.resolve("初音ミク") and restored.resolve("新条目") is None
    KnowledgeRepo.forget()


def test_restore_rejects_busy_or_changed_base_without_moving_files(restore_point):
    root, bundle, coordination = restore_point
    prepared = recovery.prepare(root, bundle.name)
    KnowledgeRepo.forget()
    with holding_activity(coordination), pytest.raises(LockUnavailable):
        recovery.activate(root, prepared["token"], coordination)
    (root / "human-note.txt").write_text("新的人改", encoding="utf-8")
    with pytest.raises(ValueError, match="prepare again"):
        recovery.activate(root, prepared["token"], coordination)
    assert (root / "human-note.txt").read_text(encoding="utf-8") == "新的人改"
    with pytest.raises(ValueError, match="Invalid backup"):
        recovery.prepare(root, "../outside")


def test_restore_rejects_tampered_snapshot(restore_point):
    root, bundle, _ = restore_point
    (bundle / "knowledge" / "knowledge.sqlite").write_bytes(b"damaged")
    with pytest.raises(ValueError, match="checksum"):
        recovery.prepare(root, bundle.name)


def test_interrupted_directory_swap_never_initializes_an_empty_store(restore_point):
    root, bundle, coordination = restore_point
    prepared = recovery.prepare(root, bundle.name)
    KnowledgeRepo.forget()
    directory = Path(prepared["path"])
    previous = directory / "previous"
    previous.mkdir()
    root.rename(previous / "knowledge")  # A simulated process death between renames.
    recovery.pending_path(root).write_text(json.dumps({"token": prepared["token"], "knowledge_root": str(root)}), encoding="utf-8")
    from desktop.backend.knowledge.schema_guard import prepare_knowledge_store
    with pytest.raises(ValueError, match="no empty store"):
        prepare_knowledge_store(root)
    assert not root.exists()
    assert recovery.recover_interrupted(root, coordination)["recovered"]
    assert KnowledgeRepo.open(root).resolve("新条目")
    assert not recovery.pending_path(root).exists()
    KnowledgeRepo.forget()
