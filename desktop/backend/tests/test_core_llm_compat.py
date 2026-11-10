"""Offline migration contracts; run with both pinned core source trees."""
from __future__ import annotations

import inspect
import ast
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from finesub.config import clear_config_cache
from finesub.llm.routing.model_routes import default_model_routes
from finesub.llm.routing.execution_policy import load_execution_settings
from desktop.backend.common.core_compat import (
    check_retired_route_choices, llm_call_options, profile_for_request, unified_llm_contract,
)
from desktop.backend.common.models import BatchItemRequest, TaskDefaults, TaskRequest
from desktop.backend.common.models import BatchRequest
from desktop.backend.settings.local_agents import COMMANDS_ENV
from desktop.backend.settings.preferences import PreferencesStore
from desktop.backend.worker.batch_main import _item_options
from desktop.backend.worker.main import _execute_pipeline
from desktop.backend.worker.model_source import source_route


@pytest.fixture(autouse=True)
def isolated_routes(tmp_path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text('[llm]\nexecution_policy="agent-only"\n', encoding="utf-8")
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(config))
    monkeypatch.delenv("GEMINI_FREE", raising=False)
    monkeypatch.delenv("GEMINI_PAID", raising=False)
    clear_config_cache()
    default_model_routes.cache_clear()
    yield
    clear_config_cache()
    default_model_routes.cache_clear()


@pytest.mark.parametrize("legacy", ["collect", "read"])
def test_knowledge_spelling_is_canonical_in_tasks_defaults_and_preferences(tmp_path, legacy):
    request = TaskRequest(input="字幕_日本語.wav", knowledge=legacy)
    assert request.knowledge == request.model_dump()["knowledge"] == "read"
    defaults = TaskDefaults(knowledge=legacy, llm_agent="LOCAL_CODEBUDDY")
    assert defaults.model_dump() == {"knowledge": "read", "llm_agent": "LOCAL_CODEBUDDY"}
    preferences = PreferencesStore(tmp_path / "user-data")
    preferences.save(task_defaults=defaults.model_dump())
    assert preferences.load().task_defaults.model_dump() == defaults.model_dump()


def test_single_and_batch_use_the_same_media_and_knowledge_boundary():
    request = TaskRequest(input="a.wav", llm_media="video", llm_correction_media="audio",
                          llm_planning_media="text", knowledge="collect")
    route = SimpleNamespace(correction_media="text", planning_media="video")
    seen = {}
    _execute_pipeline(request, stage="raw-srt", task_id="one", route=route,
                      pipeline=lambda source, **kwargs: seen.update(kwargs))
    row = BatchItemRequest.model_validate({**request.model_dump(), "llm_correction_media": "text", "llm_planning_media": "video"})
    batch = _item_options(row, {"llm": 1}, task_id="many-1")
    for key, value in llm_call_options(request, route=route).items():
        assert seen[key] == batch[key] == value
    if unified_llm_contract():
        assert seen["llm_media"] == "text"
        assert seen["knowledge"] == "read"
        assert "llm_correction_media" not in seen and "llm_planning_media" not in batch
    else:
        assert seen["llm_media"] == "video"
        assert seen["llm_planning_media"] == "video"
        assert seen["knowledge"] == "collect"


def _core_pipeline_signature():
    # Read the installed/source signature without importing torch/GPU modules.
    path = importlib.util.find_spec("finesub.stages").origin
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_pipeline")
    return inspect.Signature([
        *[inspect.Parameter(arg.arg, inspect.Parameter.POSITIONAL_OR_KEYWORD) for arg in function.args.args],
        *[inspect.Parameter(arg.arg, inspect.Parameter.KEYWORD_ONLY, default=None) for arg in function.args.kwonlyargs],
    ])


def test_pipeline_kwargs_bind_to_the_actual_core_without_running_it():
    signature = _core_pipeline_signature()
    request = TaskRequest(input="a.wav", knowledge="read")
    def bind_only(source, **kwargs):
        return signature.bind(source, **kwargs)
    bound = _execute_pipeline(request, stage="raw-srt", task_id="offline", pipeline=bind_only)
    assert bound.arguments["input_path"] == "a.wav"


def test_profile_conversion_uses_the_effective_correction_media():
    request = TaskRequest(input="a.wav", llm_media="audio", llm_correction_media="text",
                          llm_retrieval="none")
    assert profile_for_request(request).correction_media == "text"


def test_frontend_contract_is_reported_even_with_a_broken_custom_route(tmp_path, monkeypatch):
    from finesub.llm.routing import model_routes
    from desktop.backend.settings.store import SettingsStore

    def broken():
        raise ValueError("invalid custom preset")
    monkeypatch.setattr(model_routes, "default_model_routes", broken)
    settings = SettingsStore(tmp_path).routing_settings()
    assert settings.error
    assert settings.unified_llm_media is unified_llm_contract()


def test_retired_route_history_is_visible_but_cannot_be_submitted(tmp_path, monkeypatch):
    from desktop.backend.jobs import history
    from desktop.backend.settings.store import SettingsStore

    archived = {"task_id": "old", "state": "completed", "request": {
        "input": "a.wav", "llm_difficulty": "high", "knowledge": "collect",
        "llm_model": ["correction-text=removed-vendor-model"],
    }}
    monkeypatch.setattr(history.task_index, "read", lambda *_args: [archived])
    rows = history.read_history_file(None)
    assert len(rows) == 1
    assert rows[0].request.llm_difficulty == "quality"
    assert rows[0].request.knowledge == "read"
    assert rows[0].request.llm_model == archived["request"]["llm_model"]
    with pytest.raises(ValidationError, match="unknown LLM model"):
        TaskRequest.model_validate(rows[0].request.model_dump())
    saved = rows[0].request.model_copy(update={"stage": "final-srt"})
    error = SettingsStore(tmp_path).validate_request(saved)
    assert error is not None and error.code == "route_unavailable"


def test_batch_history_keeps_retired_model_choices(tmp_path):
    from desktop.backend.batches.manager import BatchManager

    history = tmp_path / "batches.json"
    history.write_text(json.dumps([{
        "batch_id": "old", "state": "completed", "created_at": 1, "updated_at": 2, "items": [],
        "request": {"items": [{"input": "a.wav", "llm_model": ["removed-target"], "knowledge": "collect"}]},
    }]), encoding="utf-8")
    manager = BatchManager(python_executable="not-run", worker_env={}, history_path=history, output_root=tmp_path / "tasks")
    assert manager.history()[0].request.items[0].llm_model == ["removed-target"]
    assert manager.history()[0].request.items[0].knowledge == "read"


def test_static_manifest_uses_only_current_core_keywords_and_roundtrips(tmp_path):
    from desktop.backend.batches.manager import BatchManager

    # The manager's static import/export needs neither a worker nor torch.
    manager = object.__new__(BatchManager)
    request = BatchRequest(items=[BatchItemRequest(input="中文_日本語.wav", knowledge="collect",
        llm_media="video", llm_correction_media="text", llm_planning_media="audio")])
    path = tmp_path / "batch.jsonl"
    manager.export_manifest(path, request)
    row = json.loads(path.read_text(encoding="utf-8"))
    aliases = {"model": "model_name", "gap": "gap_sec", "separator_rate": "separator_sample_rate"}
    core_keys = {aliases.get(key, key) for key in row if key not in {"source", "group", "priority", "_desktop"}}
    assert not (core_keys - _core_pipeline_signature().parameters.keys())
    if unified_llm_contract():
        assert row["llm_media"] == "text" and row["knowledge"] == "read"
        assert "llm_correction_media" not in row and "llm_planning_media" not in row
    else:
        assert row["knowledge"] == "collect" and row["llm_planning_media"] == "audio"
    imported, ignored = manager.import_manifest(path)
    assert not ignored
    assert llm_call_options(imported.items[0]) == llm_call_options(request.items[0])


def test_batch_guard_precedes_the_actual_core_item_build(tmp_path, monkeypatch):
    from desktop.backend.worker import batch_main
    from finesub.scheduler import BatchItem, ItemResult

    order = []
    source = tmp_path / "a.wav"
    source.write_bytes(b"audio")
    monkeypatch.setattr(batch_main, "_prepare_task_knowledge",
        lambda row, **kwargs: order.append(("guard", row.input, kwargs.get("config_files"))))
    def build(options, **kwargs):
        order.append(("build", options["source"]))
        return BatchItem(label="a.wav", stages={}, payload={})
    batch_main.run_batch_request(
        BatchRequest(items=[BatchItemRequest(input=str(source))]), batch_id="safe", batch_root=tmp_path / "batch",
        emit=lambda _: None, build_item=build, claims=object(),
        run_batch=lambda items, **kwargs: [ItemResult(label="a.wav", status="done", payload={})],
        default_pipeline_paths=lambda *_args, **_kwargs: SimpleNamespace(),
    )
    assert order == [("guard", str(source), {"config.toml": tmp_path / "config.toml"}), ("build", str(source))]


def test_single_worker_backs_up_original_config_not_generated_route_overlay(tmp_path, monkeypatch):
    from desktop.backend.knowledge import schema_guard

    original = tmp_path / "config.toml"
    root = tmp_path / "knowledge"
    monkeypatch.setenv("FINESUB_KNOWLEDGE_ROOT", str(root))
    monkeypatch.setenv("GEMINI_FREE", "offline-test-key")
    monkeypatch.setenv("FINESUB_MODEL_CATALOG", str(tmp_path / "absent-catalog"))
    request = TaskRequest(input="video", stage="final-srt", llm_source="api")
    seen = []
    monkeypatch.setattr(schema_guard, "prepare_knowledge_store", lambda value, **kwargs: seen.append((value, kwargs)))
    with source_route(request) as route:
        import os
        assert Path(os.environ["FINESUB_CONFIG_FILE"]) != original
        assert route.backup_files == {"config.toml": original}
        _execute_pipeline(request, stage="final-srt", task_id="safe",
            pipeline=lambda *_args, **_kwargs: None, route=route)
    assert seen == [(root, {"config_files": {"config.toml": original}})]


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 contract")
@pytest.mark.parametrize("choices", [
    {"llm_source": "agent", "llm_agent": "LOCAL_WORKBUDDY"},
    {"llm_model": ["planning-mm=correction-capable"]},
    {"llm_model": ["workbuddy-capable"]},
])
def test_retired_agent_and_task_bindings_are_not_silently_reassigned(choices):
    request = TaskRequest.model_validate({"input": "a.wav", **choices}, context={"archive": True})
    with pytest.raises(ValueError, match="WorkBuddy|Retired model route"):
        check_retired_route_choices(request)


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 independent CodeBuddy")
def test_codebuddy_is_explicit_only_and_keeps_its_vetted_fallback(monkeypatch):
    from desktop.backend.settings.local_agents import install_local_agent_command_overrides
    from finesub.llm.routing.execution_policy import driver_for_provider_tier, load_execution_settings

    monkeypatch.setenv(COMMANDS_ENV, json.dumps({"LOCAL_CODEBUDDY": ["codebuddy.exe"]}))
    install_local_agent_command_overrides()
    automatic = TaskRequest(input="a.wav", stage="final-srt", llm_source="auto")
    with source_route(automatic) as route:
        assert route.skip_reason and not route.targets
        assert "CodeBuddy" in route.skip_reason
    selected = automatic.model_copy(update={"llm_source": "agent", "llm_agent": "LOCAL_CODEBUDDY"})
    with source_route(selected) as route:
        expected = default_model_routes().model_groups["codebuddy-capable"].target_ids
        assert route.targets == expected
        assert route.correction_media == "text"
        assert all(default_model_routes().target_fact(target).provider_tier == "LOCAL_CODEBUDDY" for target in route.targets)
        driver = driver_for_provider_tier(load_execution_settings(), provider_tier="LOCAL_CODEBUDDY", model="glm-5.3-flash")
        assert driver.driver_id == "codebuddy"
        assert driver.config.command == ("codebuddy.exe",)


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 independent CodeBuddy")
def test_codebuddy_discovery_and_picker_use_official_npm_entry_only(tmp_path, monkeypatch):
    from desktop.backend.settings import local_agents

    monkeypatch.setattr(local_agents, "refresh_windows_path", lambda env: env.get("PATH", ""))
    bin_dir = tmp_path / "npm"
    package = bin_dir / "node_modules" / "@tencent-ai" / "codebuddy-code"
    entry = package / "bin" / "codebuddy"
    entry.parent.mkdir(parents=True)
    entry.write_bytes(b"cli")
    (package / "package.json").write_text('{"name":"@tencent-ai/codebuddy-code"}', encoding="utf-8")
    node = bin_dir / "node.exe"
    node.write_bytes(b"node")
    env = {"PATH": str(bin_dir), "USERPROFILE": str(tmp_path / "home"), "LOCALAPPDATA": str(tmp_path / "local")}
    commands = local_agents.discover_local_agent_commands(environ=env, source_roots=[],
        preferred_paths={"LOCAL_WORKBUDDY": str(tmp_path / "WorkBuddy")})
    assert commands["LOCAL_CODEBUDDY"] == (str(node.resolve()), str(entry.resolve()))
    assert "LOCAL_WORKBUDDY" not in commands
    assert local_agents.validated_agent_path("LOCAL_CODEBUDDY", str(bin_dir), env)[1] == commands["LOCAL_CODEBUDDY"]
    assert local_agents.validated_agent_path("LOCAL_CODEBUDDY", str(entry), env)[1] == commands["LOCAL_CODEBUDDY"]
    managed = tmp_path / "WorkBuddy" / "cli" / "bin" / "codebuddy"
    managed.parent.mkdir(parents=True)
    managed.write_bytes(b"managed")
    with pytest.raises(ValueError, match="独立安装"):
        local_agents.validated_agent_path("LOCAL_CODEBUDDY", str(managed), env)
    entry.unlink()
    assert "LOCAL_CODEBUDDY" not in local_agents.discover_local_agent_commands(environ=env, source_roots=[])


def test_login_launch_is_shell_free_and_only_runs_the_explicit_selected_cli(tmp_path, monkeypatch):
    from desktop.backend.launcher import bridge as module

    seen = []
    monkeypatch.setattr(module, "LOCAL_AGENT_TIERS", ("LOCAL_CODEBUDDY",))
    command = (str(tmp_path / "node.exe"), str(tmp_path / "bin" / "codebuddy"))
    monkeypatch.setattr(module, "validated_agent_path", lambda tier, selected: (selected, command))
    monkeypatch.setattr(module.subprocess, "Popen", lambda argv, **kwargs: seen.append((argv, kwargs)))
    instance = object.__new__(module.DesktopBridge)
    instance.settings = SimpleNamespace(user_data=tmp_path)
    instance.get_agent_paths = lambda: {"data": {"paths": {"LOCAL_CODEBUDDY": str(tmp_path)}}}
    result = instance.open_codebuddy_login()
    assert result["ok"]
    assert seen[0][0] == list(command)
    assert not seen[0][1].get("shell", False)
    assert seen[0][1]["creationflags"] == getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
