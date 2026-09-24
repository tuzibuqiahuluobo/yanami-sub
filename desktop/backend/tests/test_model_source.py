from __future__ import annotations

import json

import pytest

from finesub.config import clear_config_cache
from finesub.llm.routing.execution_policy import load_execution_settings
from finesub.llm.routing.model_routes import default_model_routes

from desktop.backend.common.models import TaskRequest
from desktop.backend.settings.local_agents import COMMANDS_ENV
from desktop.backend.worker.model_source import source_route


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("[llm]\nexecution_policy = \"agent-text-preferred\"\n", encoding="utf-8")
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(config))
    monkeypatch.delenv("GEMINI_FREE", raising=False)
    monkeypatch.delenv("GEMINI_PAID", raising=False)
    monkeypatch.delenv(COMMANDS_ENV, raising=False)
    clear_config_cache()
    default_model_routes.cache_clear()
    yield
    clear_config_cache()
    default_model_routes.cache_clear()


def test_auto_source_uses_free_api_when_key_is_present(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_FREE", "test-key")
    monkeypatch.setenv(COMMANDS_ENV, json.dumps({"LOCAL_DSH": ["dsh.exe"]}))
    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="auto")

    with source_route(request) as route:
        assert route.source == "api"
        assert route.targets
        assert all(
            default_model_routes().target_fact(target).provider_tier == "GEMINI_FREE"
            for target in route.targets
        )
        assert load_execution_settings().policy_id == "api-only"

    assert load_execution_settings().policy_id == "agent-text-preferred"


def test_agent_source_tries_installed_agents_in_settings_order_with_vetted_models(
    monkeypatch,
) -> None:
    monkeypatch.setenv(COMMANDS_ENV, json.dumps({
        "LOCAL_DSH": ["dsh.exe"],
        "LOCAL_CLAUDE": ["claude.exe"],
    }))
    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="agent")

    with source_route(request) as route:
        assert route.source == "agent"
        tiers = [default_model_routes().target_fact(target).provider_tier for target in route.targets]
        assert tiers[0] == "LOCAL_CLAUDE"
        assert tiers[-1] == "LOCAL_DSH"
        assert tiers == sorted(tiers)
        assert "local-dsh-deepseek-v4-pro" in route.targets
        assert "local-dsh-deepseek-v4-flash" in route.targets
        assert default_model_routes().model_groups[route.models[0]].target_ids == route.targets
        assert load_execution_settings().policy_id == "agent-only"


def test_missing_free_key_and_agent_returns_raw_subtitle_fallback() -> None:
    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="auto")

    with source_route(request) as route:
        assert route.source == "agent"
        assert route.targets == ()
        assert route.skip_reason


def test_source_group_identity_is_stable_across_retries(monkeypatch) -> None:
    monkeypatch.setenv(COMMANDS_ENV, json.dumps({"LOCAL_DSH": ["dsh.exe"]}))
    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="agent")

    with source_route(request) as first:
        first_group = first.models[0]
    with source_route(request) as second:
        assert second.models == [first_group]
