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


<<<<<<< HEAD
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
    """

    missing = [name for name in ("correction-capable", "correction-basic")
               if name not in routes.model_groups]
    if missing:
        logger.warning(
            "model routing: expected group(s) %s not found in FineSub config; "
            "treating as zero correction-capable targets", missing,
        )
    return {
=======
def _meets_correction_floor(routes, target_id: str) -> bool:
    """Check if a target meets the correction quality floor.

    Uses FineSub's quality_score mechanism instead of group membership.
    This allows any target (including Claude Code, Codex, and future agents)
    to qualify for correction as long as it meets the quality threshold,
    without requiring explicit inclusion in correction-capable groups.
    """
    task_groups = getattr(routes, "task_groups", {})
    correction_group = task_groups.get("correction-text")
    if correction_group is None:
        logger.warning(
            "model routing: correction-text task group not found; "
            "falling back to quality_score >= 70"
        )
        floor = 70
    else:
        floor = getattr(correction_group, "floor_score", 70)

    target = routes.target_fact(target_id)
    quality = getattr(target, "quality_score", 0)
    return quality >= floor


def _correction_capable_targets(routes) -> set[str]:
    """Every target that meets correction quality requirements.

    RC6.13+: Changed from group membership check to quality_score check.
    This fixes the issue where Claude Code, Codex, and other unvetted agents
    were excluded because they weren't in correction-capable/correction-basic
    groups, even though they meet the quality threshold.

    For packaged agent groups (AGY, DSH, WorkBuddy), we trust the upstream
    group membership and don't re-filter. For unvetted tiers and API targets,
    we use the quality floor check.
    """
    # For API targets: use the standard correction groups as before
    correction_targets = {
>>>>>>> codex/rc6-ui-feedback
        target_id
        for group_name in ("correction-capable", "correction-basic")
        for target_id in routes.model_groups.get(group_name, _EmptyModelGroup()).target_ids
    }

<<<<<<< HEAD
=======
    # For all agent targets: add those meeting the quality floor
    # This includes both packaged groups and unvetted tiers
    for target in routes.targets.values():
        if target.backend == "local_agent" and _meets_correction_floor(routes, target.id):
            correction_targets.add(target.id)

    return correction_targets

>>>>>>> codex/rc6-ui-feedback

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

<<<<<<< HEAD
    # Only models FineSub itself binds to correction belong in the task-wide
    # override. Its catalog also contains search-only targets (notably Gemma),
    # whose small windows make correction preflight reject the entire task.
=======
    # RC6.13+: Use correction-capable group order instead of catalog order.
    # This ensures models are tried in upstream's preferred order (e.g., 3.7
    # before 3.8 for free tier, as 3.8 uses ~1.5x thinking with no quality gain).
    # Also filters out models below correction quality floor (e.g., 3.5-lite at
    # quality 60 when floor is 70).
>>>>>>> codex/rc6-ui-feedback
    selected: list[str] = []

    # Get the ordered list from correction-capable and correction-basic groups
    capable_group = routes.model_groups.get("correction-capable", _EmptyModelGroup())
    basic_group = routes.model_groups.get("correction-basic", _EmptyModelGroup())

    # Use group order (capable first, then basic), but filter by availability
    ordered_targets = list(capable_group.target_ids) + list(basic_group.target_ids)

    for target_id in ordered_targets:
        if target_id not in correction_targets:
            continue
        target = routes.targets.get(target_id)
        if target is None or target.backend in {"local_agent", "conversational_agent"}:
            continue
        fact = routes.target_fact(target_id)
        if free_only and fact.provider_tier != "GEMINI_FREE":
            continue
        # Check if model meets correction quality floor
        if not _meets_correction_floor(routes, target_id):
            logger.debug(
                "model routing: API target %s below correction floor, skipping",
                target_id
            )
            continue
        provider = routes.provider_for_target(target_id)
        key_name = provider.key_env or target.enabled_by
        if key_name and not os.environ.get(key_name, "").strip():
            continue
        selected.append(target_id)

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


<<<<<<< HEAD
=======
def _check_media_support(routes, targets: tuple[str, ...], media: str) -> bool:
    """Check if any target supports the required media type."""
    if media == "text":
        return True  # All targets support text
    for target_id in targets:
        target = routes.target_fact(target_id)
        if media == "audio" and getattr(target, "supports_audio", False):
            return True
        if media == "video" and getattr(target, "supports_video", False):
            return True
    return False


>>>>>>> codex/rc6-ui-feedback
@contextmanager
def source_route(request: TaskRequest) -> Iterator[SourceRoute]:
    """Supply a private route group, never editing the shared config.toml.

    RC6.13+: When using agent source and selected targets don't support the
    requested media type (audio/video), automatically downgrade correction
    and planning media to 'text' to allow text-only agents (DSH, WorkBuddy,
    Claude Code, Codex) to work.
    """

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
<<<<<<< HEAD
    if not targets:
        yield _no_targets_route(source, explicit=not auto)
        return
=======

    # Enhanced logging: report why no targets are available
    if not targets:
        if source == "agent":
            logger.warning(
                "No agent targets available. Check that agents are configured "
                "and enabled in settings. COMMANDS_ENV: %s",
                os.environ.get(COMMANDS_ENV, "{}"),
            )
        else:
            logger.warning(
                "No API targets available. Check API keys. "
                "GEMINI_FREE: %s, GEMINI_PAID: %s",
                "configured" if os.environ.get("GEMINI_FREE") else "missing",
                "configured" if os.environ.get("GEMINI_PAID") else "missing",
            )
        yield _no_targets_route(source, explicit=not auto)
        return

    # RC6.13+: Auto-downgrade media to text for text-only agents
    # Check if targets support the requested media type
    routes = default_model_routes()
    correction_media = request.llm_correction_media or request.llm_media
    planning_media = request.llm_planning_media or request.llm_media

    media_downgraded = False
    if source == "agent":
        # Check if any target supports the required media
        if correction_media in ("audio", "video") and not _check_media_support(routes, targets, correction_media):
            logger.info(
                "Media auto-downgrade: selected agents don't support %s for correction, "
                "downgrading to text (agents: %s)",
                correction_media, ", ".join(targets)
            )
            correction_media = "text"
            media_downgraded = True

        if planning_media in ("audio", "video") and not _check_media_support(routes, targets, planning_media):
            logger.info(
                "Media auto-downgrade: selected agents don't support %s for planning, "
                "downgrading to text (agents: %s)",
                planning_media, ", ".join(targets)
            )
            planning_media = "text"
            media_downgraded = True

    if media_downgraded:
        logger.warning(
            "纯文本纠错已启用（所选 Agent 不支持音频/视频）。"
            "纠错质量可能低于多模态模式，因为无法利用音频佐证。"
        )
>>>>>>> codex/rc6-ui-feedback

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

        # Build config updates
        config_updates = {
            "llm": {
                "execution_policy": "agent-only" if source == "agent" else "api-only"
            }
        }

        # Apply media downgrades if needed
        if media_downgraded:
            config_updates["llm"]["correction_media"] = correction_media
            config_updates["llm"]["planning_media"] = planning_media

        update_config_file(task_config, config_updates)

        with task_config.open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n[llm.model_groups.{group_id}]\n"
                f"targets = {json.dumps(list(targets), ensure_ascii=False)}\n"
            )
        try:
            os.environ["FINESUB_CONFIG_FILE"] = str(task_config)
            clear_config_cache()
            default_model_routes.cache_clear()
            logger.info(
                "Model routing: source=%s, targets=%s, group_id=%s%s",
                source, targets, group_id,
                f", media downgraded to text" if media_downgraded else ""
            )
            yield SourceRoute(models=[group_id], source=source, targets=targets)
        finally:
            if previous is None:
                os.environ.pop("FINESUB_CONFIG_FILE", None)
            else:
                os.environ["FINESUB_CONFIG_FILE"] = previous
            clear_config_cache()
            default_model_routes.cache_clear()
