import pytest

from desktop.backend.common.core_compat import effective_task_request, preset_defaults, unified_llm_contract
from desktop.backend.common.models import BatchRequest, TaskRequest
from desktop.backend.worker.model_source import source_route


pytestmark = pytest.mark.skipif(not unified_llm_contract(), reason="0.6 preset contract")


def test_preset_uses_core_defaults_without_rewriting_old_task():
    old = TaskRequest(input="a.mp4", llm_preset="fast")
    assert effective_task_request(old) is old
    request = old.model_copy(update={"llm_preset_defaults": True})
    resolved = effective_task_request(request)
    expected = preset_defaults("fast")
    assert all(getattr(resolved, key) == value for key, value in expected.items() if key != "knowledge")
    assert resolved.llm_media == "text"
    assert resolved.llm_difficulty == "efficiency"
    assert resolved.knowledge == "update"
    assert old.llm_difficulty == "intermediate" and old.knowledge == "update"


def test_task_preset_is_scoped_and_unknown_is_rejected(tmp_path, monkeypatch):
    from finesub.config import clear_config_cache
    from finesub.llm.routing.model_routes import default_model_routes

    config = tmp_path / "config.toml"
    config.write_text('[llm]\npreset="default"\n', encoding="utf-8")
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(config))
    clear_config_cache()
    default_model_routes.cache_clear()
    before = config.read_bytes()
    with source_route(TaskRequest(input="a.mp4", stage="final-srt", llm_preset="fast", llm_preset_defaults=True)):
        assert default_model_routes().active_preset_id == "fast"
    assert config.read_bytes() == before
    assert default_model_routes().active_preset_id == "default"
    with pytest.raises(ValueError, match="Unknown task preset|known preset"):
        effective_task_request(TaskRequest(input="a.mp4", llm_preset="missing", llm_preset_defaults=True))


def test_batch_presets_must_agree():
    with pytest.raises(ValueError, match="same preset"):
        BatchRequest(items=[{"input": "a", "llm_preset": "fast"}, {"input": "b"}])
