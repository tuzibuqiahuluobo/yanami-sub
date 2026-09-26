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


def test_auto_source_with_no_key_and_no_agent_yields_raw_fallback_not_error() -> None:
    """Symmetric with the pre-existing Agent case: 'auto' picked a source on
    the person's behalf, so an empty candidate list degrades gracefully
    instead of aborting the task. (Duplicate of
    test_missing_free_key_and_agent_returns_raw_subtitle_fallback, kept
    explicit here to pin the "auto => never raise" contract regardless of
    which source auto happened to resolve to.)
    """

    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="auto")

    with source_route(request) as route:
        assert route.skip_reason
        assert route.targets == ()


def test_explicit_api_source_with_no_key_raises() -> None:
    """Regression guard for the asymmetry this patch removes: previously an
    explicit 'api' selection with no usable key/model always raised, while
    an explicit 'agent' selection with no installed Agent silently degraded
    to a raw-subtitle skip. Both now raise, because the person explicitly
    asked for a source that turns out to be unusable -- surfacing that is
    more useful than quietly delivering an uncorrected transcript.
    """

    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="api")

    with pytest.raises(ValueError):
        with source_route(request):
            pass


def test_explicit_agent_source_with_no_agent_now_raises_like_api_does() -> None:
    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="agent")

    with pytest.raises(ValueError):
        with source_route(request):
            pass


def test_agent_unvetted_tier_excludes_non_correction_targets(monkeypatch) -> None:
    """LOCAL_CLAUDE has no entry in `packaged_groups`, so it goes through the
<<<<<<< HEAD
    naming-convention fallback path. Before this patch that path never
    checked correction capability at all; assert here that a target the
    fixture's own `correction-capable`/`correction-basic` groups do not list
    is never selected, even if it would otherwise match the "-native-"
    heuristic.
=======
    quality-floor check path.

    RC6.13+: Changed from group membership check to quality_score >= floor.
    Assert that targets meeting the quality threshold are selected, regardless
    of whether they're in correction-capable/correction-basic groups.
>>>>>>> codex/rc6-ui-feedback
    """

    monkeypatch.setenv(COMMANDS_ENV, json.dumps({"LOCAL_CLAUDE": ["claude.exe"]}))
    request = TaskRequest(input="a.mp4", stage="final-srt", llm_source="agent")

    routes = default_model_routes()
<<<<<<< HEAD
    correction_targets = {
        target_id
        for group_name in ("correction-capable", "correction-basic")
        for target_id in routes.model_groups[group_name].target_ids
    }

    with source_route(request) as route:
        assert route.targets  # LOCAL_CLAUDE is still usable for its real targets
        assert set(route.targets) <= correction_targets
=======
    task_groups = getattr(routes, "task_groups", {})
    correction_group = task_groups.get("correction-text")
    floor = getattr(correction_group, "floor_score", 70) if correction_group else 70

    with source_route(request) as route:
        assert route.targets  # LOCAL_CLAUDE is still usable for its real targets
        # All selected targets should meet the quality floor
        for target_id in route.targets:
            target = routes.target_fact(target_id)
            quality = getattr(target, "quality_score", 0)
            assert quality >= floor, f"Target {target_id} quality {quality} below floor {floor}"

>>>>>>> codex/rc6-ui-feedback
