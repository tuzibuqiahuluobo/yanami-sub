from __future__ import annotations

import json

import pytest

from finesub.config import clear_config_cache
from finesub.llm.routing.capabilities import check_model_group_windows
from finesub.llm.routing.execution_policy import load_execution_settings
from finesub.llm.routing.model_routes import default_model_routes

from desktop.backend.common.models import TaskRequest
from desktop.backend.settings.local_agents import COMMANDS_ENV
from desktop.backend.worker.main import _routing_override
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


@pytest.mark.parametrize(
    ("source", "free_key", "paid_key"),
    [("auto", True, False), ("api", True, True), ("api", False, True)],
)
def test_api_route_excludes_search_only_models_and_passes_correction_preflight(
    monkeypatch, source: str, free_key: bool, paid_key: bool,
) -> None:
    if free_key:
        monkeypatch.setenv("GEMINI_FREE", "test-free-key")
    if paid_key:
        monkeypatch.setenv("GEMINI_PAID", "test-paid-key")
    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source=source)

    with source_route(request) as route, _routing_override(route.models):
        assert route.source == "api"
        assert "gemini-free-3_6-flash" in route.targets or not free_key
        assert "gemini-paid-3_8-flash" in route.targets or not paid_key
        assert not {"gemini-free-3_1-flash-lite", "gemini-free-2_5-flash",
                    "gemini-free-gemma-4-31b"}.intersection(route.targets)
        assert default_model_routes().model_groups[route.models[0]].target_ids == route.targets
        check_model_group_windows()


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
