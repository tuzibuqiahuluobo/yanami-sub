from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3

import pytest

from desktop.backend.knowledge import schema_guard
from desktop.backend.knowledge import backup as snapshots
from finesub.llm.knowledge.node import schema


@pytest.fixture(autouse=True)
def no_personal_config_backup(monkeypatch):
    monkeypatch.setattr(snapshots, "config_sources", lambda: {})


def seed(root: Path, version: int) -> Path:
    root.mkdir()
    database = root / "knowledge.sqlite"
    with closing(schema.connect(database)) as connection:
        schema.init_schema(connection)
        connection.execute("UPDATE meta SET value=? WHERE key='schema_version'", (str(version),))
        connection.execute("CREATE TABLE test_text (value TEXT)")
        connection.execute("INSERT INTO test_text VALUES ('人工润色・中文・日本語')")
    return database


def stored_version(database: Path) -> int:
    with closing(schema_guard._reader(database)) as connection:
        return schema_guard._version(connection)


def backups(root: Path) -> list[Path]:
    return list((root.parent / "knowledge-backups").glob("*/knowledge/knowledge.sqlite"))


def test_no_store_or_current_schema_creates_no_backup(tmp_path):
    root = tmp_path / "knowledge"
    assert schema_guard.prepare_knowledge_store(root) is None
    assert not root.exists()
    database = seed(root, schema.SCHEMA_VERSION)
    before = database.read_bytes()
    assert schema_guard.prepare_knowledge_store(root) is None
    assert database.read_bytes() == before
    assert not backups(root)


def test_backup_is_verified_and_precedes_core_migration(tmp_path, monkeypatch):
    root = tmp_path / "中文知识库"
    old = schema.SCHEMA_VERSION - 1
    database = seed(root, old)
    original = schema.init_schema
    calls = []

    def migrate(connection):
        files = backups(root)
        assert len(files) == 1
        assert snapshots.verify_backup(files[0])["schema_version"] == old
        assert stored_version(files[0]) == old
        calls.append(True)
        return original(connection)

    monkeypatch.setattr(schema, "init_schema", migrate)
    backup = schema_guard.prepare_knowledge_store(root)
    assert backup == backups(root)[0]
    assert calls == [True]
    assert stored_version(database) == schema.SCHEMA_VERSION
    assert stored_version(backup) == old
    with closing(schema_guard._reader(backup)) as connection:
        assert connection.execute("SELECT value FROM test_text").fetchone()[0] == "人工润色・中文・日本語"
        assert connection.execute("PRAGMA quick_check").fetchall() == [("ok",)]
    assert schema_guard.prepare_knowledge_store(root) is None
    assert len(backups(root)) == 1


def test_committed_wal_content_is_in_backup(tmp_path):
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION - 1)
    with closing(schema.connect(database)) as writer:
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO test_text VALUES ('仅在 WAL 里的已提交内容')")
        assert database.with_name(database.name + "-wal").stat().st_size > 0
        backup = schema_guard.prepare_knowledge_store(root)
        with closing(schema_guard._reader(backup)) as connection:
            assert connection.execute("SELECT count(*) FROM test_text").fetchone()[0] == 2


@pytest.mark.skipif(schema.SCHEMA_VERSION != 6, reason="5 -> 6 transition is exercised with the 0.6.0 core")
def test_schema_5_backup_does_not_contain_the_new_human_ack_table(tmp_path):
    root = tmp_path / "knowledge"
    database = seed(root, 5)
    with closing(schema.connect(database)) as connection:
        connection.execute("DROP TABLE line_acks")
    backup = schema_guard.prepare_knowledge_store(root)
    with closing(schema_guard._reader(backup)) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='line_acks'").fetchone() is None
        assert schema_guard._version(connection) == 5
    with closing(schema_guard._reader(database)) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='line_acks'").fetchone()[0] == "line_acks"
        assert schema_guard._version(connection) == 6


def test_backup_failure_leaves_original_schema_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION - 1)
    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(snapshots.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        schema_guard.prepare_knowledge_store(root)
    assert stored_version(database) == schema.SCHEMA_VERSION - 1
    assert not backups(root)
    assert not list((root.parent / "knowledge-backups").glob("*.tmp"))


def test_backup_timeout_leaves_original_schema_unchanged(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION - 1)
    monkeypatch.setattr(schema_guard, "_BACKUP_TIMEOUT_SECONDS", -1)
    with pytest.raises(TimeoutError, match="timed out"):
        schema_guard.prepare_knowledge_store(root)
    assert stored_version(database) == schema.SCHEMA_VERSION - 1
    assert not backups(root)


def test_backup_verification_failure_does_not_upgrade(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION - 1)
    connect = sqlite3.connect

    class FailingCheck(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql == "PRAGMA quick_check":
                return super().execute("SELECT 'backup failed integrity check'")
            return super().execute(sql, *args, **kwargs)

    def connection(path, **kwargs):
        if str(path).endswith(".sqlite.tmp"):
            kwargs["factory"] = FailingCheck
        return connect(path, **kwargs)

    monkeypatch.setattr(snapshots.sqlite3, "connect", connection)
    with pytest.raises(RuntimeError, match="Invalid knowledge backup"):
        schema_guard.prepare_knowledge_store(root)
    assert stored_version(database) == schema.SCHEMA_VERSION - 1
    assert not backups(root)


def test_migration_failure_keeps_backup_without_automatic_restore(tmp_path, monkeypatch):
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION - 1)
    def fail(*_):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(schema, "init_schema", fail)
    with pytest.raises(RuntimeError, match="backup:"):
        schema_guard.prepare_knowledge_store(root)
    assert stored_version(database) == schema.SCHEMA_VERSION - 1
    assert len(backups(root)) == 1


def test_newer_or_corrupt_database_is_not_migrated(tmp_path):
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION + 1)
    before = database.read_bytes()
    with pytest.raises(ValueError, match="Newer knowledge schema"):
        schema_guard.prepare_knowledge_store(root)
    assert database.read_bytes() == before
    assert not backups(root)
    database.write_bytes(b"not SQLite")
    with pytest.raises(sqlite3.DatabaseError):
        schema_guard.prepare_knowledge_store(root)
    assert database.read_bytes() == b"not SQLite"


def test_busy_knowledge_store_does_not_begin_migration(tmp_path, monkeypatch):
    from finesub.llm.knowledge import base
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION - 1)

    @contextmanager
    def busy(_root):
        yield False

    monkeypatch.setattr(base, "knowledge_write_lock", busy)
    with pytest.raises(RuntimeError, match="busy"):
        schema_guard.prepare_knowledge_store(root)
    assert stored_version(database) == schema.SCHEMA_VERSION - 1
    assert not backups(root)


def test_concurrent_preparation_migrates_once(tmp_path):
    root = tmp_path / "knowledge"
    database = seed(root, schema.SCHEMA_VERSION - 1)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(schema_guard.prepare_knowledge_store, [root] * 3))
    assert len([result for result in results if result is not None]) == 1
    assert stored_version(database) == schema.SCHEMA_VERSION
    assert len(backups(root)) == 1


def test_knowledge_worker_prepares_store_before_opening_it(tmp_path, monkeypatch):
    from desktop.backend.worker import knowledge_main
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    calls = []
    monkeypatch.setattr(schema_guard, "prepare_knowledge_store", lambda value: calls.append(value))
    monkeypatch.setattr(knowledge_main, "_snapshot", lambda: {"ready": bool(calls)})
    assert knowledge_main._dispatch({"action": "snapshot"}) == {"ready": True}
    assert calls == [root.resolve()]


@pytest.mark.parametrize("stage, count", [("raw-srt", 1), ("translated-srt", 1), ("final-srt", 1)])
def test_single_and_batch_pipeline_entry_use_the_same_guard(tmp_path, monkeypatch, stage, count):
    from desktop.backend.common.models import TaskRequest
    from desktop.backend.worker.main import _execute_pipeline
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    calls = []
    monkeypatch.setattr(schema_guard, "prepare_knowledge_store", lambda value: calls.append(value))
    _execute_pipeline(TaskRequest(input="input.mp4"), stage=stage, task_id="test", pipeline=lambda *args, **kwargs: None)
    assert calls == [root.resolve()] * count


def test_guard_failure_prevents_processing_instead_of_migrating_unprotected(tmp_path, monkeypatch):
    from desktop.backend.common.models import TaskRequest
    from desktop.backend.worker.main import _execute_pipeline
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))

    def fail(_root):
        raise OSError("backup not possible")

    monkeypatch.setattr(schema_guard, "prepare_knowledge_store", fail)
    calls = []
    with pytest.raises(OSError, match="backup not possible"):
        _execute_pipeline(TaskRequest(input="input.mp4"), stage="final-srt", task_id="test", pipeline=lambda *args, **kwargs: calls.append(True))
    assert calls == []


def test_explicitly_disabled_knowledge_and_style_do_not_open_the_store(tmp_path, monkeypatch):
    from desktop.backend.common.models import TaskRequest
    from desktop.backend.worker.main import _execute_pipeline
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    calls = []
    monkeypatch.setattr(schema_guard, "prepare_knowledge_store", lambda value: calls.append(value))
    request = TaskRequest(input="input.mp4", knowledge="none", style_mode="none")
    assert _execute_pipeline(request, stage="final-srt", task_id="test", pipeline=lambda *args, **kwargs: "done") == "done"
    assert calls == []


@pytest.mark.parametrize("stage, count", [("aligned", 1), ("raw-srt", 1), ("vocal", 0)])
def test_asr_knowledge_context_is_protected_without_an_llm_stage(tmp_path, monkeypatch, stage, count):
    from desktop.backend.common.models import TaskRequest
    from desktop.backend.worker.main import _execute_pipeline
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    calls = []
    monkeypatch.setattr(schema_guard, "prepare_knowledge_store", lambda value: calls.append(value))
    request = TaskRequest(input="input.mp4", asr_context="terms", knowledge="read", style_mode="none")
    _execute_pipeline(request, stage=stage, task_id="test", pipeline=lambda *args, **kwargs: None)
    assert calls == [root.resolve()] * count
