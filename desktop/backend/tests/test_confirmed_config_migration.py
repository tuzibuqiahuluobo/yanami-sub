import hashlib
import json
from pathlib import Path

import pytest

from desktop.backend.common.core_compat import unified_llm_contract
from desktop.backend.settings import core_migration as migration


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "中文_日本語.toml"
    path.write_bytes(b'[llm]\ncorrection_media="text"\nplanning_media="audio"\n')
    monkeypatch.setenv("FINESUB_MODEL_CATALOG", str(tmp_path / "absent"))
    return path


def test_old_core_cannot_apply_new_contract(config):
    if unified_llm_contract():
        pytest.skip("legacy core only")
    assert migration.preview_config_migration(config)["status"] == "legacy"
    with pytest.raises(ValueError):
        migration.apply_config_migration(config, "0" * 64, confirmed=True)


@pytest.fixture
def modern(config):
    if not unified_llm_contract():
        pytest.skip("0.6.0 confirmed media conversion")
    return config


def test_preview_is_read_only_and_apply_preserves_comments_crlf_and_private_backup(modern):
    original = ('# 私人说明\r\n[llm]\r\ncorrection_media = \'text\' # 纠错注释\r\n'
                'planning_media = "audio" # 规划注释\r\n[private]\r\nkey="private-test-key"\r\n').encode("utf-8")
    modern.write_bytes(original)
    before_files = set(modern.parent.iterdir())
    plan = migration.preview_config_migration(modern)
    assert plan["status"] == "ready" and len(plan["changes"]) == 2
    assert "private-test-key" not in json.dumps(plan)
    assert modern.read_bytes() == original and set(modern.parent.iterdir()) == before_files
    result = migration.apply_config_migration(modern, plan["token"], confirmed=True)
    current = modern.read_bytes()
    assert b"correction_media" not in current and b"planning_media" not in current
    assert "media = 'text' # 纠错注释\r\n".encode() in current
    assert "# 规划注释\r\n".encode() in current and b"\r\r\n" not in current
    assert b'[private]\r\nkey="private-test-key"\r\n' in current
    backup = Path(result["backup_path"])
    assert (backup / "config.toml").read_bytes() == original
    receipt = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert receipt["files"]["config.toml"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert migration.preview_config_migration(modern)["status"] == "current"
    with pytest.raises(ValueError, match="stale"):
        migration.apply_config_migration(modern, plan["token"], confirmed=True)
    assert len(list((modern.parent / "config-backups").iterdir())) == 1


@pytest.mark.parametrize("body", [
    '[llm]\nmedia="video"\ncorrection_media="text"\n',
    '[llm]\nplanning_media="audio"\n',
    '[llm]\ncorrection_media="invalid"\n',
    '[llm]\n"correction_media"="text"\n',
    '[llm]\ncorrection_media="text"\n[llm.model_groups.old]\ntargets=["retired-model"]\n',
    '[llm]\ncorrection_media="text"\n[private]\nvalue="""multi\nline"""\n',
])
def test_ambiguous_complex_or_invalid_routing_is_blocked_without_any_write(modern, body):
    modern.write_text(body, encoding="utf-8")
    original = modern.read_bytes()
    plan = migration.preview_config_migration(modern)
    assert plan["status"] == "blocked" and not plan["token"]
    assert modern.read_bytes() == original and not (modern.parent / "config-backups").exists()


def test_existing_equal_media_can_remove_legacy_keys_without_changing_it(modern):
    modern.write_text('[llm]\nmedia="text"\ncorrection_media="text" # 旧说明\nplanning_media="audio"\n', encoding="utf-8")
    plan = migration.preview_config_migration(modern)
    assert plan["status"] == "ready"
    migration.apply_config_migration(modern, plan["token"], confirmed=True)
    assert 'media="text"' in modern.read_text(encoding="utf-8")
    assert "# 旧说明" in modern.read_text(encoding="utf-8")


def test_explicit_confirmation_and_matching_preview_are_required(modern):
    plan = migration.preview_config_migration(modern)
    with pytest.raises(ValueError, match="confirmation"):
        migration.apply_config_migration(modern, plan["token"])
    assert not (modern.parent / "config-backups").exists()
    modern.write_bytes(modern.read_bytes() + b"# edited after preview\n")
    after = modern.read_bytes()
    with pytest.raises(ValueError, match="stale"):
        migration.apply_config_migration(modern, plan["token"], confirmed=True)
    assert modern.read_bytes() == after and not (modern.parent / "config-backups").exists()


def test_catalog_changes_invalidate_preview_and_catalog_is_backed_up(modern, monkeypatch):
    from finesub.llm.routing.model_catalog import _catalog_path
    catalog = modern.parent / "catalog.toml"
    catalog.write_bytes(_catalog_path().read_bytes())
    monkeypatch.setenv("FINESUB_MODEL_CATALOG", str(catalog))
    plan = migration.preview_config_migration(modern)
    assert plan["status"] == "ready", plan
    catalog.write_bytes(catalog.read_bytes() + b"\n# catalog edited\n")
    with pytest.raises(ValueError, match="stale"):
        migration.apply_config_migration(modern, plan["token"], confirmed=True)
    plan = migration.preview_config_migration(modern)
    result = migration.apply_config_migration(modern, plan["token"], confirmed=True)
    assert (Path(result["backup_path"]) / "model_catalog.toml").read_bytes() == catalog.read_bytes()


def test_backup_failure_never_writes_original(modern, monkeypatch):
    plan = migration.preview_config_migration(modern)
    original = modern.read_bytes()
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(migration.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        migration.apply_config_migration(modern, plan["token"], confirmed=True)
    assert modern.read_bytes() == original and not list((modern.parent / "config-backups").iterdir())


def test_write_failure_keeps_verified_backup_without_overwriting_source(modern, monkeypatch):
    from finesub_bootstrap import fsops
    plan, original = migration.preview_config_migration(modern), modern.read_bytes()
    write = fsops.write_atomic
    def fail(path, *args, **kwargs):
        if path == modern:
            raise OSError("write refused")
        return write(path, *args, **kwargs)
    monkeypatch.setattr(fsops, "write_atomic", fail)
    with pytest.raises(OSError, match="write refused"):
        migration.apply_config_migration(modern, plan["token"], confirmed=True)
    assert modern.read_bytes() == original
    assert next((modern.parent / "config-backups").glob("*/config.toml")).read_bytes() == original


def test_edit_during_backup_is_not_overwritten(modern, monkeypatch):
    from finesub_bootstrap import fsops
    plan = migration.preview_config_migration(modern)
    write = fsops.write_atomic
    changed = b'[llm]\nmedia="video"\n# user changed file\n'
    def edit(path, *args, **kwargs):
        result = write(path, *args, **kwargs)
        if path.name == "manifest.json":
            modern.write_bytes(changed)
        return result
    monkeypatch.setattr(fsops, "write_atomic", edit)
    with pytest.raises(ValueError, match="Config changed"):
        migration.apply_config_migration(modern, plan["token"], confirmed=True)
    assert modern.read_bytes() == changed


def test_bridge_requires_idle_activity_and_reports_applied_config_even_if_refresh_fails(modern):
    from types import SimpleNamespace
    from desktop.backend.launcher.bridge import DesktopBridge
    from finesub_bootstrap.locks import holding_activity
    bridge = object.__new__(DesktopBridge)
    bridge.settings = SimpleNamespace(config_path=modern, user_data=modern.parent / "user-data")
    def fail_refresh():
        raise RuntimeError("restart needed")
    bridge._refresh_worker_environment = fail_refresh
    plan = bridge.preview_config_migration()["data"]
    assert bridge.apply_config_migration(plan["token"])["error"]["code"] == "config_migration_failed"
    with holding_activity(bridge.settings.user_data):
        assert bridge.apply_config_migration(plan["token"], True)["error"]["code"] == "config_migration_busy"
    result = bridge.apply_config_migration(plan["token"], True)
    assert result["ok"] and result["data"]["restart_required"]
    assert migration.preview_config_migration(modern)["status"] == "current"
