from pathlib import Path

import pytest

from finesub import config as app_config
from desktop.backend.common.models import RoutingUpdate, TaskRequest
from desktop.backend.settings.store import SettingsStore
from desktop.backend.settings.local_agents import COMMANDS_ENV
from finesub_bootstrap import secrets
from finesub.llm.routing.api_keys import (
    EXA_POOL,
    GEMINI_FREE_POOL,
    GEMINI_PAID_POOL,
    TAVILY_POOL,
    resolve_pool,
)
from finesub.llm.routing.model_routes import default_model_routes


class _FakeBackend:
    """Deterministic KEK stand-in so machine-bound behavior is testable."""

    def __init__(self, machine: bytes = b"machine-A") -> None:
        self.machine = machine

    def wrap(self, data: bytes) -> bytes:
        return self.machine + b"|" + data

    def unwrap(self, blob: bytes) -> bytes:
        prefix = self.machine + b"|"
        if not blob.startswith(prefix):
            raise secrets.SecretUnreadable("wrapped on another machine")
        return blob[len(prefix):]


@pytest.fixture()
def fake_backend():
    backend = _FakeBackend()
    secrets.set_backend(backend)
    yield backend
    secrets.set_backend(None)


@pytest.fixture(autouse=True)
def isolate_core_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(COMMANDS_ENV, raising=False)
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    app_config.clear_config_cache()
    default_model_routes.cache_clear()
    yield
    app_config.clear_config_cache()
    default_model_routes.cache_clear()


def test_missing_api_key_keeps_raw_srt_available(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)

    capabilities = store.get_capabilities()

    assert capabilities.raw_srt is True
    assert capabilities.translation is False
    assert store.validate_stage("raw-srt") is None


def test_translation_request_without_gemini_key_returns_structured_error(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path)

    error = store.validate_stage("final-srt")

    assert error is not None
    assert error.code == "api_key_required"
    assert error.action == "open_settings"


def test_worker_environment_contains_saved_keys_without_exposing_them(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path)
    store.save_api_keys(gemini="secret-g", exa="", tavily="secret-t")

    public = store.public_settings().model_dump(mode="json")
    worker_env = store.build_worker_env()

    assert public["api_keys"] == {
        "gemini_free": "configured",
        "gemini_paid": "missing",
        "exa": "missing",
        "tavily": "configured",
    }
    assert "secret-g" not in str(public)
    assert worker_env == {
        "GEMINI_FREE": "secret-g",
        "TAVILY_KEYS": "secret-t",
    }


def test_api_keys_round_trip_through_private_env_file(tmp_path: Path) -> None:
    SettingsStore(tmp_path).save_api_keys(
        gemini="line-safe-key",
        exa="exa-key",
        tavily="",
    )

    reloaded = SettingsStore(tmp_path)

    assert reloaded.build_worker_env() == {
        "GEMINI_FREE": "line-safe-key",
        "EXA_KEYS": "exa-key",
    }
    assert (tmp_path / ".env").is_file()


def test_api_keys_export_to_a_plaintext_transfer_file(
    fake_backend, tmp_path: Path
) -> None:
    store = SettingsStore(tmp_path / "user-data")
    store.save_api_keys(gemini="secret-g", tavily="secret-t")
    destination = tmp_path / "transfer.env"

    result = store.export_api_keys(destination)

    assert result == {"path": str(destination.resolve()), "count": 2}
    assert destination.read_text(encoding="utf-8") == (
        "GEMINI_FREE=secret-g\nTAVILY_KEYS=secret-t\n"
    )
    assert "secret-g" not in store.env_path.read_text(encoding="utf-8")


def test_api_key_export_never_overwrites_the_protected_store(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)

    with pytest.raises(ValueError, match="不能用明文"):
        store.export_api_keys(store.env_path)


def test_legacy_desktop_keys_are_migrated_once(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            (
                "GEMINI_API_KEY=legacy-gemini",
                "EXA_API_KEY=legacy-exa",
                "TAVILY_API_KEY=legacy-tavily",
                "",
            )
        ),
        encoding="utf-8",
    )

    worker_env = SettingsStore(tmp_path).build_worker_env()
    migrated = env_path.read_text(encoding="utf-8")

    assert worker_env == {
        "GEMINI_FREE": "legacy-gemini",
        "EXA_KEYS": "legacy-exa",
        "TAVILY_KEYS": "legacy-tavily",
    }
    assert "GEMINI_API_KEY" not in migrated
    assert "EXA_API_KEY" not in migrated
    assert "TAVILY_API_KEY" not in migrated


def test_saved_keys_are_visible_to_cli_provider_pools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("GEMINI_FREE", "GEMINI_PAID", "EXA_KEYS", "TAVILY_KEYS"):
        monkeypatch.delenv(name, raising=False)
    store = SettingsStore(tmp_path)
    store.save_api_keys(
        gemini="gemini-key",
        gemini_paid="paid-key",
        exa="exa-key",
        tavily="tavily-key",
    )
    worker_env = store.build_worker_env()

    assert [
        entry.key
        for entry in resolve_pool(GEMINI_FREE_POOL, worker_env, config={})
    ] == ["gemini-key"]
    assert [
        entry.key
        for entry in resolve_pool(GEMINI_PAID_POOL, worker_env, config={})
    ] == ["paid-key"]
    assert [
        entry.key
        for entry in resolve_pool(EXA_POOL, worker_env, config={})
    ] == ["exa-key"]
    assert [
        entry.key
        for entry in resolve_pool(TAVILY_POOL, worker_env, config={})
    ] == ["tavily-key"]


def test_delete_api_key_removes_only_selected_provider(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)
    store.save_api_keys(gemini="g", exa="e", tavily="t")

    store.delete_api_key("gemini")

    assert store.build_worker_env() == {
        "EXA_KEYS": "e",
        "TAVILY_KEYS": "t",
    }


def test_saved_keys_are_ciphertext_on_disk_but_plaintext_for_workers(
    fake_backend, tmp_path: Path
) -> None:
    store = SettingsStore(tmp_path)
    store.save_api_keys(gemini="secret-gemini-key-123")

    text = (tmp_path / ".env").read_bytes().decode("utf-8")
    assert "secret-gemini-key-123" not in text
    assert "GEMINI_FREE=fs$" in text
    assert "FINESUB_KEYRING=finesub$kek$v1$" in text
    assert store.build_worker_env() == {"GEMINI_FREE": "secret-gemini-key-123"}


def test_keyring_line_survives_every_save(fake_backend, tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)
    store.save_api_keys(gemini="secret-gemini-key-123")
    keyring_line = next(
        line
        for line in (tmp_path / ".env").read_bytes().decode("utf-8").splitlines()
        if line.startswith("FINESUB_KEYRING=")
    )

    store.save_api_keys(tavily="secret-tavily-key-456")
    store.delete_api_key("gemini")

    lines = (tmp_path / ".env").read_bytes().decode("utf-8").splitlines()
    assert keyring_line in lines


def test_unreadable_values_degrade_to_missing_without_losing_the_line(
    fake_backend, tmp_path: Path
) -> None:
    store = SettingsStore(tmp_path)
    store.save_api_keys(gemini="secret-gemini-key-123")
    gemini_line = next(
        line
        for line in (tmp_path / ".env").read_bytes().decode("utf-8").splitlines()
        if line.startswith("GEMINI_FREE=")
    )

    secrets.set_backend(_FakeBackend(b"machine-B"))  # .env visits another PC
    store_on_b = SettingsStore(tmp_path)
    assert store_on_b.get_capabilities().translation is False
    assert store_on_b.public_settings().api_keys["gemini_free"] == "missing"

    # Saving another provider there must not delete what it cannot read.
    store_on_b.save_api_keys(tavily="new-tavily-key-on-b")
    lines = (tmp_path / ".env").read_bytes().decode("utf-8").splitlines()
    assert gemini_line in lines

    secrets.set_backend(fake_backend)  # back home: everything still opens
    assert SettingsStore(tmp_path).build_worker_env()["GEMINI_FREE"] == (
        "secret-gemini-key-123"
    )


def test_reveal_api_keys_reports_entries_with_labels(
    fake_backend, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        'GEMINI_FREE={"main":"AIzaMainKey1234567","spare":"AIzaSpareKey7654321"}\n',
        encoding="utf-8",
    )
    secrets.protect_env_file(env_path)

    revealed = SettingsStore(tmp_path).reveal_api_keys()

    assert revealed["gemini_free"] == [
        {
            "name": "main",
            "key": "AIzaMainKey1234567",
            "masked": "AIza…4567",
        },
        {
            "name": "spare",
            "key": "AIzaSpareKey7654321",
            "masked": "AIza…4321",
        },
    ]
    assert revealed["gemini_paid"] == []
    assert revealed["exa"] == []
    assert revealed["tavily"] == []


def test_paid_gemini_alone_enables_translation_and_reaches_the_worker(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path)

    store.save_api_keys(gemini_paid="paid-only")

    assert store.get_capabilities().translation is True
    assert store.validate_stage("final-srt") is None
    assert store.build_worker_env() == {"GEMINI_PAID": "paid-only"}


def test_native_retrieval_requires_a_configured_native_search_route(
    tmp_path: Path,
):
    store = SettingsStore(tmp_path)
    store._read_keys = lambda: {"GEMINI_FREE": "free-only"}  # type: ignore[method-assign]
    request = TaskRequest(input="D:/media/a.mp4", stage="final-srt", llm_retrieval="native")

    error = store.validate_request(request)

    assert error is not None
    assert error.code == "native_search_unavailable"
    assert error.action == "open_settings"


def test_paid_native_route_passes_the_launch_guard(tmp_path: Path):
    store = SettingsStore(tmp_path)
    store._read_keys = lambda: {"GEMINI_PAID": "paid-only"}  # type: ignore[method-assign]
    request = TaskRequest(input="D:/media/a.mp4", stage="final-srt", llm_retrieval="native")

    assert store.validate_request(request) is None


def test_selected_target_must_have_its_own_credential(
    tmp_path: Path,
) -> None:
    store = SettingsStore(tmp_path)
    store._read_keys = lambda: {"GEMINI_FREE": "free-only"}  # type: ignore[method-assign]
    request = TaskRequest(
        input="D:/media/a.mp4",
        stage="final-srt",
        llm_model=["gemini-paid-3_8-flash"],
    )

    error = store.validate_stage(request.stage, request.llm_model)

    assert error is not None
    assert error.code == "route_unavailable"
    assert error.action is None


def test_routing_catalog_marks_saved_api_targets_available(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)
    store._read_keys = lambda: {"GEMINI_FREE": "free-only"}  # type: ignore[method-assign]

    routing = store.routing_settings()
    free_targets = [
        target
        for target in routing.targets
        if target.provider_tier == "GEMINI_FREE"
    ]
    paid_targets = [
        target
        for target in routing.targets
        if target.provider_tier == "GEMINI_PAID"
    ]

    assert free_targets and all(target.available for target in free_targets)
    assert paid_targets and not any(target.available for target in paid_targets)


def test_routing_settings_are_projected_from_the_core_catalog(tmp_path: Path) -> None:
    routing = SettingsStore(tmp_path).routing_settings()

    assert routing.error == ""
    assert routing.active_preset_id == "default"
    assert {preset.id for preset in routing.presets} >= {
        "default",
        "agy-hybrid",
        "agy",
    }
    assert routing.model_groups
    assert any(target.backend == "local_agent" for target in routing.targets)


def test_routing_update_writes_validated_scalar_core_settings(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path)
    current = store.routing_settings()

    saved = store.save_routing_settings(
        RoutingUpdate(
            preset="agy-hybrid",
            execution_policy=current.execution_policy,
            local_agent_timeout_seconds=900,
            local_agent_allow_unisolated_user_config=False,
            local_agent_service_tier="fast",
            local_agent_reasoning_effort="high",
            local_agent_max_parallel=3,
        )
    )

    config = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert saved.active_preset_id == "agy-hybrid"
    assert saved.local_agent_timeout_seconds == 900
    assert saved.local_agent_service_tier == "fast"
    assert saved.local_agent_reasoning_effort == "high"
    assert saved.local_agent_max_parallel == 3
    assert 'preset = "agy-hybrid"' in config
