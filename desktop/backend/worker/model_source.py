"""One-task model source selection using FineSub's ordered group fallback."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import logging
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

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceRoute:
    models: list[str]
    source: str
    targets: tuple[str, ...] = ()
    skip_reason: str = ""


@dataclass(frozen=True)
class _EmptyModelGroup:
    """Stand-in for a missing model group so lookups degrade instead of crash.

    FineSub's config format is an upstream contract this repo does not
    control (see docs/core-compatibility.md). If a future core version
    renames or removes ``correction-capable`` / ``correction-basic``, we
    want that to surface as "no correction models available" -- the same
    graceful-skip path a missing API key already takes -- rather than an
    unhandled KeyError that aborts the whole task or batch.
    """

    target_ids: tuple[str, ...] = field(default_factory=tuple)


def _agent_tiers() -> set[str]:
    try:
        commands = json.loads(os.environ.get(COMMANDS_ENV, "{}"))
    except (TypeError, ValueError):
        return set()
    if not isinstance(commands, dict):
        return set()
    return {tier for tier, command in commands.items() if command}


def _correction_capable_targets(routes) -> set[str]:
    """Every target FineSub itself binds to correction, from either source.

    Centralized so both the API branch and the local-Agent branch of
    `_targets` apply the *same* capability check. Previously only the API
    branch filtered against this set; the Agent branch trusted its packaged
    groups (and a naming-convention heuristic for unvetted tiers) to already
    be correction-only, which is exactly the assumption that let a
    search-only model slip into the task model group in the bug RC6.10 was
    meant to fix. A missing group name resolves to an empty set instead of
    raising, so a config mismatch degrades to "no targets" rather than
    crashing the task.

    RC6.11+: Also includes targets from local agent capability groups
    (dsh-capable, agy-only-capable, workbuddy-capable) since these are
    verified correction-capable models that the upstream finesub config
    hasn't yet added to the correction-capable/correction-basic groups.
    """

    missing = [name for name in ("correction-capable", "correction-basic")
               if name not in routes.model_groups]
    if missing:
        logger.warning(
            "model routing: expected group(s) %s not found in FineSub config; "
            "treating as zero correction-capable targets", missing,
        )

    # Get correction targets from the standard groups
    correction_targets = {
        target_id
        for group_name in ("correction-capable", "correction-basic")
        for target_id in routes.model_groups.get(group_name, _EmptyModelGroup()).target_ids
    }

    # RC6.11+: Add local agent targets from their packaged capability groups
    # These are correction-capable but not yet included in the upstream
    # finesub correction groups due to configuration mismatch
    local_agent_groups = ("dsh-capable", "dsh-basic", "agy-only-capable",
                          "workbuddy-capable", "workbuddy-basic")
    for group_name in local_agent_groups:
        group = routes.model_groups.get(group_name)
        if group:
            correction_targets.update(group.target_ids)
            logger.debug(
                "model routing: added %d targets from %s to correction-capable set",
                len(group.target_ids), group_name
            )

    return correction_targets


def _targets(source: str, *, free_only: bool) -> tuple[str, ...]:
    routes = default_model_routes()
    correction_targets = _correction_capable_targets(routes)

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
                # Defense in depth: a packaged group is expected to be
                # correction-only already, but we no longer *only* trust
                # that convention -- the same explicit check the API branch
                # uses is applied here too.
                dropped = [
                    target_id for target_id in group.target_ids
                    if routes.target_fact(target_id).provider_tier == tier
                    and target_id not in correction_targets
                ]
                if dropped:
                    logger.warning(
                        "model routing: packaged group %r for tier %s contains "
                        "non-correction target(s) %s; excluding from task model group",
                        packaged_groups[tier], tier, dropped,
                    )
                selected.extend(
                    target_id for target_id in group.target_ids
                    if routes.target_fact(target_id).provider_tier == tier
                    and target_id in correction_targets
                )
                continue
            candidates = [
                target.id for target in routes.targets.values()
                if target.backend == "local_agent"
                and routes.target_fact(target.id).provider_tier == tier
                # Unvetted tiers (anything not in packaged_groups, e.g. a
                # newly detected CLI) must clear the same correction-capable
                # bar the API branch enforces -- the earlier version chose a
                # "primary" purely by the "-native-" naming convention, with
                # no guarantee it could actually do correction/translation.
                and target.id in correction_targets
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


def _no_targets_route(source: str, *, explicit: bool) -> SourceRoute:
    """Build the "nothing to try" route for either source, symmetrically.

    Previously an empty Agent candidate list produced a graceful
    `skip_reason` (keep the raw subtitle) while an empty API candidate list
    raised `ValueError` and aborted the whole task -- even though the two
    situations ("no local Agent detected" vs. "no API key/model available")
    are the same kind of problem from the pipeline's point of view. A single
    misconfigured or rate-limited item in a batch should not take down every
    other item in that batch.

    We keep one asymmetry, deliberately: when the person *explicitly* chose
    this source for this task (not "auto"), we still want that surfaced
    loudly rather than silently degrading to raw subtitles, because a
    deliberate choice with zero usable targets is very likely a
    configuration mistake the person should fix before spending a full task
    run on it. The desktop's "new task" form should already block submission
    in this case (see NewTask.tsx / TaskSettings.tsx validation); this is the
    worker-side backstop for batches and any path that reaches the worker
    without going through that form validation.
    """

    reason = (
        "没有可用的本地 Agent，纠错翻译已跳过；保留原始字幕。" if source == "agent" else
        "没有可用的 API 模型（请检查 API 密钥），纠错翻译已跳过；保留原始字幕。"
    )
    if explicit:
        raise ValueError(
            "没有可用的" + ("本地 Agent" if source == "agent" else "API 模型")
            + "；请检查 API 密钥或改选其他来源，或改用自动模式以启用跳过纠错翻译的兜底。"
        )
    return SourceRoute(models=[], source=source, skip_reason=reason)


@contextmanager
def source_route(request: TaskRequest) -> Iterator[SourceRoute]:
    """Supply a private route group, never editing the shared config.toml."""

    if request.stage not in {"translated-srt", "final-srt"} or request.llm_source == "manual":
        yield SourceRoute(models=request.llm_model, source="manual")
        return

    free_key = bool(os.environ.get("GEMINI_FREE", "").strip())
    auto = request.llm_source == "auto"
    source = (
        "api" if auto and free_key else
        "agent" if auto else request.llm_source
    )
    targets = _targets(source, free_only=auto and source == "api")
    if not targets:
        yield _no_targets_route(source, explicit=not auto)
        return

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
