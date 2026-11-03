"""Temporary 0.5.1 -> 0.6.0 call boundary, not another settings resolver.

Keep explicit choices from existing desktop tasks. Only translate the two
retired spellings here; the core still owns defaults, routing and validation.
Remove the legacy branch when the runtime/build pin moves to 0.6.0.
"""

from __future__ import annotations

from typing import Any


def preset_defaults(preset_id: str = "") -> dict[str, Any]:
    from dataclasses import replace
    from finesub.llm.correction_request import resolve_switches
    from finesub.llm.routing.model_routes import default_model_routes

    routes = default_model_routes()
    if preset_id:
        if preset_id not in routes.presets:
            raise ValueError(f"未知任务预设 / Unknown task preset: {preset_id}")
        routes = replace(routes, active_preset_id=preset_id)
    switches = resolve_switches({}, routes=routes)
    return {
        "llm_media": switches.media, "llm_retrieval": switches.retrieval,
        "llm_difficulty": switches.difficulty, "llm_continuity": switches.continuity,
        "llm_parallel_windows": switches.parallel_windows, "knowledge": switches.knowledge,
    }


def effective_task_request(request: Any):
    if not getattr(request, "llm_preset_defaults", False):
        return request
    if not unified_llm_contract():
        raise ValueError("任务预设继承需要 FineSub 0.6.0 / Task presets require FineSub 0.6.0")
    return request.model_copy(update={**preset_defaults(request.llm_preset),
        "llm_correction_media": "", "llm_planning_media": "", "llm_preset_defaults": False})


def unified_llm_contract() -> bool:
    # Inspect the contract, not installed package metadata: source checkouts
    # can override an older installed distribution on PYTHONPATH.
    from finesub.llm.routing.model_routes import TASK_GROUP_IDS

    return "planning-text" not in TASK_GROUP_IDS


def llm_call_options(request: Any, *, route: Any = None, knowledge: str | None = None) -> dict[str, Any]:
    request = effective_task_request(request)
    correction = route.correction_media if route is not None else request.llm_correction_media
    mode = request.knowledge if knowledge is None else knowledge
    options = {
        "llm_media": request.llm_media,
        "llm_retrieval": request.llm_retrieval,
        "llm_difficulty": request.llm_difficulty,
        "llm_continuity": request.llm_continuity,
        "llm_parallel_windows": request.llm_parallel_windows,
        "llm_output_scale": request.llm_output_scale,
        "knowledge": mode,
    }
    if unified_llm_contract():
        options["llm_media"] = correction or request.llm_media
        options["knowledge"] = "read" if mode == "collect" else mode
    else:
        options["llm_correction_media"] = correction
        options["llm_planning_media"] = route.planning_media if route is not None else request.llm_planning_media
        options["knowledge"] = "collect" if mode == "read" else mode
    return options


def speech_call_options(request: Any) -> dict[str, Any]:
    keys = ("diarize", "diarize_backend", "diarize_max_speakers", "speaker_tracks")
    if unified_llm_contract():
        return {key: getattr(request, key) for key in keys}
    if request.diarize != "off" or request.speaker_tracks != "off":
        raise ValueError("说话人功能需要 FineSub 0.6.0 / Diarization requires FineSub 0.6.0")
    return {}


def profile_for_request(request: Any):
    from finesub.llm.routing.profiles import resolve_profile

    options = llm_call_options(request)
    kwargs = {
        "media": options["llm_media"],
        "retrieval": options["llm_retrieval"],
        "difficulty": options["llm_difficulty"],
        "continuity": options["llm_continuity"],
        "output_scale": options["llm_output_scale"],
    }
    if not unified_llm_contract():
        kwargs["correction_media"] = options["llm_correction_media"]
        kwargs["planning_media"] = options["llm_planning_media"]
    return resolve_profile(**kwargs)


def check_retired_route_choices(request: Any) -> None:
    """An archived choice may be displayed, but never silently rebound."""
    if not unified_llm_contract():
        return
    if request.llm_source == "agent" and request.llm_agent == "LOCAL_WORKBUDDY":
        raise ValueError(
            "FineSub 0.6.0 已移除 WorkBuddy 桌面通道。请独立安装并登录 CodeBuddy CLI，"
            "再重新选择 Agent；旧路径和登录凭据不会自动复用。 / Select the independent CodeBuddy CLI."
        )
    for row in request.llm_model:
        group, sep, target = row.partition("=")
        if group in {"planning-mm", "planning-text", "search_judge"} or (
            (target if sep else group).startswith(("local-workbuddy-", "workbuddy-"))
        ):
            raise ValueError(
                f"旧模型路由 {row!r} 已退役，请在纠错翻译设置中重新选择；"
                "不会自动改用其他模型。 / Retired model route; choose a current route."
            )
