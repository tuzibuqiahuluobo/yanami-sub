"""One-task model source selection using FineSub's ordered group fallback."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterator

from finesub.config import clear_config_cache, read_config_with_path
from finesub.llm.routing.model_routes import default_model_routes

from desktop.backend.common.models import TaskRequest
from desktop.backend.settings.config_file import update_config_file
from desktop.backend.settings.local_agents import COMMANDS_ENV


@dataclass(frozen=True)
class SourceRoute:
    models: list[str]
    source: str
    targets: tuple[str, ...] = ()
    skip_reason: str = ""


def _agent_tiers() -> set[str]:
    try:
        commands = json.loads(os.environ.get(COMMANDS_ENV, "{}"))
    except (TypeError, ValueError):
        return set()
    if not isinstance(commands, dict):
        return set()
    return {tier for tier, command in commands.items() if command}


def _targets(source: str, *, free_only: bool) -> tuple[str, ...]:
    routes = default_model_routes()
    if source == "agent":
        tiers = _agent_tiers()
        # Settings lists agents by tier. Keep each CLI's vetted packaged
        # fallback group intact (including its media/search variants) before
        # moving to the next CLI. A single first-listed model can be unavailable
        # while another model on the same Agent still works.
        packaged_groups = {
            "LOCAL_AGY": "agy-only-capable",
            "LOCAL_DSH": "dsh-capable",
            "LOCAL_WORKBUDDY": "workbuddy-capable",
        }
        selected: list[str] = []
        for tier in sorted(tiers):
            group = routes.model_groups.get(packaged_groups.get(tier, ""))
            if group is not None:
                selected.extend(
                    target_id for target_id in group.target_ids
                    if routes.target_fact(target_id).provider_tier == tier
                )
                continue
            candidates = [
                target.id for target in routes.targets.values()
                if target.backend == "local_agent"
                and routes.target_fact(target.id).provider_tier == tier
            ]
            primary = next((target for target in candidates if "-native-" not in target), None)
            if primary is None:
                continue
            selected.append(primary)
            primary_model = routes.target_fact(primary).api_model_id
            native = next(
                (target for target in candidates
                 if "-native-" in target
                 and routes.target_fact(target).api_model_id == primary_model),
                None,
            )
            if native is not None:
                selected.append(native)
        return tuple(selected)

    # Only models FineSub itself binds to correction belong in the task-wide
    # override. Its catalog also contains search-only targets (notably Gemma),
    # whose small windows make correction preflight reject the entire task.
    correction_targets = {
        target_id
        for group_name in ("correction-capable", "correction-basic")
        for target_id in routes.model_groups[group_name].target_ids
    }
    selected: list[str] = []
    for target in routes.targets.values():
        if target.id not in correction_targets or target.backend in {
            "local_agent", "conversational_agent"
        }:
            continue
        fact = routes.target_fact(target.id)
        if free_only and fact.provider_tier != "GEMINI_FREE":
            continue
        provider = routes.provider_for_target(target.id)
        key_name = provider.key_env or target.enabled_by
        if key_name and not os.environ.get(key_name, "").strip():
            continue
        selected.append(target.id)
    return tuple(selected)


@contextmanager
def source_route(request: TaskRequest) -> Iterator[SourceRoute]:
    """Supply a private route group, never editing the shared config.toml."""

    if request.stage not in {"translated-srt", "final-srt"} or request.llm_source == "manual":
        yield SourceRoute(models=request.llm_model, source="manual")
        return

    free_key = bool(os.environ.get("GEMINI_FREE", "").strip())
    source = (
        "api" if request.llm_source == "auto" and free_key else
        "agent" if request.llm_source == "auto" else request.llm_source
    )
    targets = _targets(source, free_only=request.llm_source == "auto" and source == "api")
    if not targets:
        if source == "agent":
            yield SourceRoute(
                models=[],
                source="agent",
                skip_reason="没有可用的本地 Agent，纠错翻译已跳过；保留原始字幕。",
            )
            return
        raise ValueError("没有可用的 API 模型；请检查 API 密钥或改选本地 Agent。")

    # Stable across resume: a random group id would change the routing
    # identity on every retry and invalidate FineSub's correction checkpoints.
    route_key = "\0".join((source, *targets)).encode("utf-8")
    group_id = f"yanami-source-{hashlib.sha256(route_key).hexdigest()[:16]}"
    _, shared_path = read_config_with_path()
    previous = os.environ.get("FINESUB_CONFIG_FILE")
    with tempfile.TemporaryDirectory(prefix="yanami-model-source-") as directory:
        task_config = Path(directory) / "config.toml"
        if shared_path is not None:
            shutil.copy2(shared_path, task_config)
        update_config_file(
            task_config,
            {"llm": {"execution_policy": "agent-only" if source == "agent" else "api-only"}},
        )
        with task_config.open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n[llm.model_groups.{group_id}]\n"
                f"targets = {json.dumps(list(targets), ensure_ascii=False)}\n"
            )
        try:
            os.environ["FINESUB_CONFIG_FILE"] = str(task_config)
            clear_config_cache()
            default_model_routes.cache_clear()
            yield SourceRoute(models=[group_id], source=source, targets=targets)
        finally:
            if previous is None:
                os.environ.pop("FINESUB_CONFIG_FILE", None)
            else:
                os.environ["FINESUB_CONFIG_FILE"] = previous
            clear_config_cache()
            default_model_routes.cache_clear()
