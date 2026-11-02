from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from desktop.backend.knowledge import backup, schema_guard
from finesub.llm.knowledge.node import schema


@pytest.fixture
def source(tmp_path, monkeypatch):
    root = tmp_path / "中文_日本語知识库"
    root.mkdir()
    with closing(schema.connect(root / "knowledge.sqlite")) as connection:
        schema.init_schema(connection)
        connection.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(schema.SCHEMA_VERSION - 1),))
    rendered = root / "rendered" / "common"
    rendered.mkdir(parents=True)
    (rendered / "初音ミク.md").write_text("# 初音ミク\n\n尚未收录的人工修改・日本語\n", encoding="utf-8")
    (rendered.parent / ".manifest.json").write_text('{"baseline":"原始投影"}', encoding="utf-8")
    (root / "empty-directory").mkdir()
    (root / "share-private-test.key").write_bytes(b"fake-private-test-material")
    proposals = root.parent / "knowledge-proposals"
    proposals.mkdir()
    (proposals / "pending.json").write_text('{"draft":"待应用提案"}', encoding="utf-8")
    config = tmp_path / "自定义配置.toml"
    config.write_text('[llm]\nmedia="text"\n# 用户配置\n', encoding="utf-8")
    catalog = tmp_path / "自定义目录.psv"
    catalog.write_text("model|中文_日本語\n", encoding="utf-8")
    configs = {"config.toml": config, "model_catalog.psv": catalog}
    monkeypatch.setattr(backup, "config_sources", lambda: configs)
    return root, configs


def snapshot(source):
    root, _configs = source
    database = schema_guard.prepare_knowledge_store(root)
    return database.parent.parent


def version(path):
    with closing(backup.read_database(path)) as connection:
        return backup.database_version(connection)


def test_snapshot_and_restore_preserve_dirty_projection_configs_and_receipts(source, tmp_path):
    root, configs = source
    bundle = snapshot(source)
    manifest = backup.verify_backup(bundle)
    assert manifest["schema_version"] == schema.SCHEMA_VERSION - 1
    assert not any(name.endswith(("-wal", "-shm", "-journal")) for name in manifest["files"])
    restored = backup.restore_backup(bundle, tmp_path / "恢复副本_日本語")
    if os.name != "nt":
        assert restored.stat().st_mode & 0o077 == 0
    assert backup.verify_backup(restored) == manifest
    assert version(restored / "knowledge" / "knowledge.sqlite") == schema.SCHEMA_VERSION - 1
    assert version(root / "knowledge.sqlite") == schema.SCHEMA_VERSION
    for relative in ("rendered/common/初音ミク.md", "rendered/.manifest.json", "share-private-test.key"):
        assert (restored / "knowledge" / relative).read_bytes() == (root / relative).read_bytes()
    assert (restored / "knowledge/empty-directory").is_dir()
    assert (restored / "knowledge-proposals/pending.json").read_bytes() == (root.parent / "knowledge-proposals/pending.json").read_bytes()
    for name, original in configs.items():
        assert (restored / "config" / name).read_bytes() == original.read_bytes()
        assert (restored / "config" / name).stat().st_mtime_ns == original.stat().st_mtime_ns


@pytest.mark.parametrize("location", ["existing", "live", "bundle"])
def test_restore_never_overwrites_existing_or_live_paths(source, tmp_path, location):
    root, _configs = source
    bundle = snapshot(source)
    target = {"existing": tmp_path / "existing", "live": root / "restore", "bundle": bundle / "restore"}[location]
    if location == "existing":
        target.mkdir()
        (target / "keep.txt").write_bytes(b"keep")
    with pytest.raises((ValueError, FileExistsError)):
        backup.restore_backup(bundle, target)
    if location == "existing":
        assert (target / "keep.txt").read_bytes() == b"keep"
    else:
        assert not target.exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/escape", "knowledge/../escape",
                                  "knowledge/x:stream", "knowledge/CON.txt", "knowledge/ending."])
def test_unsafe_manifest_paths_are_rejected_before_restore(source, tmp_path, name):
    bundle = snapshot(source)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][name] = {"size": 0, "sha256": "0" * 64}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="snapshot path"):
        backup.restore_backup(bundle, destination)
    assert not destination.exists()


@pytest.mark.parametrize("damage", ["checksum", "missing", "extra", "case_collision", "bad_metadata"])
def test_corrupt_or_incomplete_snapshot_is_not_restored(source, tmp_path, damage):
    bundle = snapshot(source)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = bundle / "knowledge/rendered/common/初音ミク.md"
    if damage == "checksum":
        path.write_bytes(b"changed")
    elif damage == "missing":
        path.unlink()
    elif damage == "extra":
        (bundle / "unexpected.txt").write_bytes(b"extra")
    elif damage == "case_collision":
        manifest["directories"].append("KNOWLEDGE")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        del manifest["knowledge_source"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        backup.restore_backup(bundle, destination)
    assert not destination.exists()


@pytest.mark.parametrize("change", ["edit", "new_file", "timestamp"])
def test_files_changed_during_backup_stop_migration_and_discard_only_staging(source, monkeypatch, change):
    root, _configs = source
    copy = backup._copy
    edited = False
    def changed(source_path, destination, *args):
        nonlocal edited
        copy(source_path, destination, *args)
        if edited:
            return
        edited = True
        original = root / "rendered/common/初音ミク.md"
        if change == "edit":
            original.write_text("用户继续修改", encoding="utf-8")
        elif change == "new_file":
            (root / "new.md").write_bytes(b"new")
        else:
            os.utime(original, ns=(original.stat().st_atime_ns, original.stat().st_mtime_ns + 1_000_000))
    monkeypatch.setattr(backup, "_copy", changed)
    with pytest.raises(RuntimeError, match="changed during backup"):
        schema_guard.prepare_knowledge_store(root)
    assert version(root / "knowledge.sqlite") == schema.SCHEMA_VERSION - 1
    assert not list((root.parent / "knowledge-backups").iterdir())
    assert (root / "rendered/common/初音ミク.md").is_file()


def test_unreadable_directory_is_not_silently_omitted(source, monkeypatch):
    root, _configs = source
    def cannot_walk(*_args, onerror, **_kwargs):
        onerror(PermissionError("read denied"))
        return iter(())
    monkeypatch.setattr(backup.os, "walk", cannot_walk)
    with pytest.raises(PermissionError, match="read denied"):
        schema_guard.prepare_knowledge_store(root)
    assert version(root / "knowledge.sqlite") == schema.SCHEMA_VERSION - 1


def test_existing_legacy_files_without_database_are_not_silently_initialized(tmp_path):
    root = tmp_path / "legacy"
    root.mkdir()
    original = root / "知识.md"
    original.write_bytes(b"preserve legacy knowledge")
    with pytest.raises(ValueError, match="without a database"):
        schema_guard.prepare_knowledge_store(root)
    assert not (root / "knowledge.sqlite").exists()
    assert original.read_bytes() == b"preserve legacy knowledge"


def test_linked_files_are_rejected_without_following_them(source, tmp_path):
    root, _configs = source
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside must not be copied")
    link = root / "linked"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError, match="refuses links"):
        schema_guard.prepare_knowledge_store(root)
    assert outside.read_bytes() == b"outside must not be copied"
    assert version(root / "knowledge.sqlite") == schema.SCHEMA_VERSION - 1


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction")
@pytest.mark.parametrize("operation", ["backup", "restore"])
@pytest.mark.parametrize("target_exists", [True, False])
def test_windows_junction_is_rejected_without_copying_its_target(source, tmp_path, operation, target_exists):
    root, _configs = source
    bundle = snapshot(source) if operation == "restore" else root
    outside = tmp_path / "external"
    if target_exists:
        outside.mkdir()
        (outside / "keep.txt").write_bytes(b"outside")
    link = bundle / "junction"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    with pytest.raises(ValueError, match="refuses links"):
        if operation == "backup":
            schema_guard.prepare_knowledge_store(root)
        else:
            backup.restore_backup(bundle, tmp_path / "restore")
    if target_exists:
        assert (outside / "keep.txt").read_bytes() == b"outside"
    else:
        assert not outside.exists()
    assert not (tmp_path / "restore").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows directory junction")
@pytest.mark.parametrize("target_exists", [True, False])
def test_restore_destination_never_follows_a_junction_to_a_live_or_missing_target(source, tmp_path, target_exists):
    bundle = snapshot(source)
    outside = source[0] if target_exists else tmp_path / "missing-target"
    link = tmp_path / "selected-junction"
    subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(outside)],
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
    with pytest.raises((ValueError, OSError)):
        backup.restore_backup(bundle, link)
    if not target_exists:
        assert not outside.exists()
    assert link.is_junction()
    backup.verify_backup(bundle)


def test_interrupted_restore_keeps_an_inactive_partial_copy_without_manifest(source, tmp_path, monkeypatch):
    bundle = snapshot(source)
    original = (source[0] / "knowledge.sqlite").read_bytes()
    copy = backup._copy
    calls = []
    def interrupted(*args):
        calls.append(True)
        if len(calls) == 2:
            raise OSError("interrupted copy")
        copy(*args)
    monkeypatch.setattr(backup, "_copy", interrupted)
    destination = tmp_path / "partial-copy"
    with pytest.raises(OSError, match="interrupted copy"):
        backup.restore_backup(bundle, destination)
    assert destination.is_dir() and not (destination / "manifest.json").exists()
    assert (source[0] / "knowledge.sqlite").read_bytes() == original
    backup.verify_backup(bundle)


def test_cli_verifies_and_restores_without_loading_the_core(source, tmp_path):
    bundle = snapshot(source)
    # A repair copy must work even when the target core/runtime cannot import.
    script = "import sys,runpy; sys.modules['finesub']=None; sys.argv=['backup',*sys.argv[1:]]; runpy.run_module('desktop.backend.knowledge.backup',run_name='__main__')"
    verified = subprocess.run([sys.executable, "-c", script, "verify", str(bundle)], capture_output=True, text=True, encoding="utf-8", check=True)
    assert "Verified private snapshot" in verified.stdout
    assert "fake-private" not in verified.stdout
    destination = tmp_path / "offline-restore"
    restored = subprocess.run([sys.executable, "-c", script, "restore", str(bundle), "--to", str(destination)],
        capture_output=True, text=True, encoding="utf-8", check=True)
    assert "not activated" in restored.stdout
    assert backup.verify_backup(destination) == backup.verify_backup(bundle)
