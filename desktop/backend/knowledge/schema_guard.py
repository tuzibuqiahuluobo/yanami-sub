"""Back up a knowledge database before the pinned core upgrades its schema."""
from __future__ import annotations

from contextlib import closing
import logging
from pathlib import Path
import threading

from desktop.backend.knowledge.backup import (
    create_backup, database_version as _version, read_database as _reader,
)


LOGGER = logging.getLogger(__name__)
_MIGRATION_LOCK = threading.Lock()
_BACKUP_TIMEOUT_SECONDS = 30


def prepare_knowledge_store(root: Path, *, config_files: dict[str, Path] | None = None) -> Path | None:
    """Return the verified backup, or None when no schema change is needed.

    The returned SQLite file sits inside a verified snapshot of knowledge,
    pending desktop proposals and original config files. Never restore live.
    """
    from finesub.llm.knowledge.base import knowledge_write_lock
    from finesub.llm.knowledge.node import schema

    root = root.expanduser().resolve()
    from desktop.backend.knowledge.recovery import pending_path
    if pending_path(root).exists():
        raise ValueError("检测到未完成的知识库恢复，请在知识库维护页点击‘修复未完成的恢复’；不会创建空库 / Settle the interrupted restore in Knowledge maintenance; no empty store created")
    database = root / "knowledge.sqlite"
    if not database.is_file():
        if root.exists() and any(root.iterdir()):
            raise ValueError(
                "知识库目录已有文件但缺少 knowledge.sqlite，请先离线核查或导入；"
                "原文件保持不变，不自动初始化覆盖。 / Existing knowledge files without a database"
            )
        return None
    with closing(_reader(database)) as source:
        stored = _version(source)
    expected = schema.SCHEMA_VERSION
    if stored == expected:
        return None
    if stored > expected:
        raise ValueError(
            f"知识库版本 {stored} 高于当前内核支持的 {expected}；请使用较新应用，"
            "或退出所有任务后恢复升级前备份。不会自动覆盖知识库。 / Newer knowledge schema"
        )

    with _MIGRATION_LOCK, knowledge_write_lock(root) as locked:
        if not locked:
            raise RuntimeError("知识库正在使用，无法安全升级，请稍后重试 / Knowledge base is busy")
        with closing(_reader(database)) as source:
            stored = _version(source)
            if stored == expected:
                return None
            if stored > expected:
                raise ValueError("知识库已被较新版本升级 / Knowledge schema changed")
            backup = create_backup(root, source, stored, expected,
                config_files=config_files, timeout=_BACKUP_TIMEOUT_SECONDS)

        # The core remains the only owner of migrations, under its write lock.
        try:
            with closing(schema.connect(database)) as connection:
                schema.init_schema(connection)
        except Exception as error:
            raise RuntimeError(
                f"知识库升级未完成，升级前备份已保留：{backup.parent.parent}；未自动恢复或覆盖数据。"
                f" / Knowledge migration failed; backup: {backup.parent.parent}"
            ) from error
        LOGGER.warning("知识库已从 schema %s 升至 %s；升级前备份：%s", stored, expected, backup.parent.parent)
        return backup
