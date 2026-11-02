import pytest

from finesub.config import clear_config_cache
from finesub.llm.routing.model_routes import default_model_routes
from desktop.backend.common.core_compat import unified_llm_contract
from desktop.backend.common.models import TaskRequest
from desktop.backend.settings.core_migration import check_config_migration
from desktop.backend.settings.store import SettingsStore


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "自定义配置.toml"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(path))
    monkeypatch.setenv("FINESUB_MODEL_CATALOG", str(tmp_path / "absent"))
    clear_config_cache()
    default_model_routes.cache_clear()
    yield path
    clear_config_cache()
    default_model_routes.cache_clear()


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 configuration review")
@pytest.mark.parametrize("body", [
    '[llm]\ncorrection_media="text"\n',
    '[llm]\nplanning_media="audio"\n',
    '[llm.model_groups.old]\ntargets=["local-workbuddy-deepseek-v4-flash"]\n',
    '[llm.presets.custom]\nname="旧预设"\n[llm.presets.custom.bindings]\n"planning-text/quality"="dsh-capable"\n',
])
def test_legacy_configuration_requires_review_without_editing_or_rebinding(config, body):
    config.write_text("# 保留用户注释\n" + body, encoding="utf-8")
    before = config.read_bytes()
    with pytest.raises(ValueError):
        check_config_migration(config)
    assert config.read_bytes() == before
    settings = SettingsStore(config.parent)
    error = settings.validate_request(TaskRequest(input="video", stage="final-srt", llm_source="agent"))
    assert error is not None and error.action == "open_settings"
    assert settings.validate_request(TaskRequest(input="video", stage="raw-srt")) is None


def test_current_configuration_keeps_bytes_and_core_defaults(config):
    config.write_text('# 用户注释\n[llm]\nmedia="text"\n', encoding="utf-8")
    before = config.read_bytes()
    check_config_migration(config)
    assert config.read_bytes() == before
