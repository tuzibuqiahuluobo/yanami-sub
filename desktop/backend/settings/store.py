from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from finesub.config import (
    clear_config_cache,
    config_float,
    validate_split_length_scale,
)
from finesub.paths import resolve_config_file
from desktop.backend.common.models import (
    BridgeError,
    CapabilityState,
    LocalAgentStatus,
    PipelineStage,
    PublicSettings,
    RoutingPresetSummary,
    RoutingProviderSummary,
    RoutingSettings,
    RoutingTargetSummary,
    RoutingUpdate,
    SharedSettings,
)
from finesub_bootstrap import secrets
from desktop.backend.settings.config_file import update_config_file


Provider = Literal["gemini_free", "gemini_paid", "exa", "tavily"]
ProviderInput = Literal["gemini", "gemini_free", "gemini_paid", "exa", "tavily"]

_ENV_NAMES: dict[Provider, str] = {
    "gemini_free": "GEMINI_FREE",
    "gemini_paid": "GEMINI_PAID",
    "exa": "EXA_KEYS",
    "tavily": "TAVILY_KEYS",
}
_LEGACY_ENV_NAMES: dict[Provider, str] = {
    "gemini_free": "GEMINI_API_KEY",
    "exa": "EXA_API_KEY",
    "tavily": "TAVILY_API_KEY",
}
_PROVIDER_TIER_ENV_NAMES = {
    "GEMINI_FREE": "GEMINI_FREE",
    "GEMINI_PAID": "GEMINI_PAID",
}


class SettingsStore:
    def __init__(self, user_data: Path) -> None:
        self.user_data = user_data.expanduser().resolve()
        self.env_path = self.user_data / ".env"

    def get_capabilities(self) -> CapabilityState:
        keys = self._read_keys()
        return CapabilityState(
            raw_srt=True,
            translation=self._has_llm_route(keys),
            web_search=bool(keys.get("EXA_KEYS") or keys.get("TAVILY_KEYS")),
        )

    def validate_stage(
        self, stage: PipelineStage, llm_model: list[str] | None = None
    ) -> BridgeError | None:
        if stage not in {"translated-srt", "final-srt"}:
            return None
        if self._has_llm_route(self._read_keys(), llm_model=llm_model):
            return None
        return BridgeError(
            code="api_key_required",
            message="翻译功能需要可用的 Gemini 凭据或本地 Agent 路由。",
            action="open_settings",
        )

    def validate_request(self, request) -> BridgeError | None:
        """Validate launch-time capabilities before the worker starts."""

        stage_error = self.validate_stage(request.stage, request.llm_model)
        if stage_error is not None:
            return stage_error
        if request.stage not in {"translated-srt", "final-srt"}:
            return None
        try:
            from finesub.llm.routing.capabilities import (
                CapabilityUnavailableError,
                validate_profile_capabilities,
            )
            from finesub.llm.routing.profiles import (
                SwitchConflictError,
                resolve_profile,
            )
            from finesub.llm.routing.model_routes import (
                install_runtime_preferred,
                parse_llm_model_args,
                runtime_preferred,
            )
        except (ImportError, OSError, RuntimeError):
            # Keep the settings panel usable if an optional core module is not
            # available; the worker will report the concrete import error.
            return None

        previous_routes = runtime_preferred()
        try:
            install_runtime_preferred(parse_llm_model_args(request.llm_model))
            profile = resolve_profile(
                media=request.llm_media,
                retrieval=request.llm_retrieval,
                difficulty=request.llm_difficulty,
                continuity=request.llm_continuity,
                correction_media=request.llm_correction_media,
                planning_media=request.llm_planning_media,
                output_scale=request.llm_output_scale,
            )
            if request.llm_retrieval == "native" and not self._has_native_route(
                profile,
                fast_enabled=request.llm_fast == "on",
            ):
                return BridgeError(
                    code="native_search_unavailable",
                    message=(
                        "当前模型不支持原生联网搜索。请将检索改为“本地检索”，"
                        "或在设置中选择支持原生搜索的模型。"
                    ),
                    action="open_settings",
                )
            validate_profile_capabilities(
                profile,
                fast_enabled=request.llm_fast == "on",
            )
        except CapabilityUnavailableError as error:
            if (
                request.llm_retrieval != "native"
                or "native_search" not in str(error)
            ):
                return BridgeError(
                    code="capability_unavailable",
                    message="当前翻译配置没有可用的模型，请在设置中检查路由或 API Key。",
                    action="open_settings",
                )
            return BridgeError(
                code="native_search_unavailable",
                message=(
                    "当前模型不支持原生联网搜索。请将检索改为“本地检索”，"
                    "或在设置中选择支持原生搜索的模型。"
                ),
                action="open_settings",
            )
        except SwitchConflictError as error:
            return BridgeError(code="invalid_request", message=str(error))
        except (ImportError, OSError, RuntimeError, ValueError):
            # A malformed custom route remains the core's responsibility; the
            # key/stage guard above still prevents the common misconfiguration.
            return None
        finally:
            install_runtime_preferred(previous_routes)
        return None

    def _has_native_route(self, profile, *, fast_enabled: bool) -> bool:
        """Whether a native-search chain has both the tool and a real key."""

        from finesub.llm.routing.capabilities import required_chains
        from finesub.llm.routing.model_routes import default_model_routes

        routes = default_model_routes()
        keys = self._read_keys()
        for requirement in required_chains(profile, fast_enabled=fast_enabled):
            if not requirement.needs_native_search:
                continue
            for endpoint in requirement.endpoints:
                if not endpoint.native_search_tool:
                    continue
                if endpoint.backend in {"local_agent", "conversational_agent"}:
                    return True
                try:
                    provider = routes.provider_for_target(endpoint.target_id)
                except (KeyError, ValueError):
                    continue
                env_name = provider.key_env or endpoint.provider_tier
                if keys.get(env_name):
                    return True
        return False

    def _has_llm_route(
        self,
        keys: dict[str, str],
        *,
        llm_model: list[str] | None = None,
    ) -> bool:
        """Whether the configured route has at least one callable backend.

        This is deliberately a light launch guard, not a second router. The
        core still owns media capability filtering and fallback decisions.
        """

        if keys.get("GEMINI_FREE") or keys.get("GEMINI_PAID"):
            return True
        try:
            from finesub.llm.routing.model_routes import (
                default_model_routes,
                parse_llm_model_args,
            )

            routes = default_model_routes()
            targets: set[str] = set()
            if llm_model:
                for value in parse_llm_model_args(llm_model).values():
                    if value in routes.targets:
                        targets.add(value)
                    elif value in routes.model_groups:
                        targets.update(routes.model_groups[value].target_ids)
            if not targets:
                targets.update(
                    target_id
                    for group_id in routes.reachable_group_ids()
                    for target_id in routes.model_groups[group_id].target_ids
                )
            for target_id in targets:
                target = routes.targets[target_id]
                if target.backend in {"local_agent", "conversational_agent"}:
                    return True
                provider = routes.provider_for_target(target_id)
                env_name = (
                    provider.key_env
                    or _PROVIDER_TIER_ENV_NAMES.get(provider.id, "")
                    or target.enabled_by
                )
                if env_name and keys.get(env_name):
                    return True
        except (OSError, RuntimeError, ValueError):
            # A broken custom route should be diagnosed by the core. Do not
            # turn the settings panel itself into a second config parser.
            return False
        return False

    # ------------------------------------------------- shared config.toml

    @property
    def config_path(self) -> Path:
        """Where a shared setting is written, and what the panel shows the user.

        Resolution matches every other reader (an explicit override, then the
        source checkout, then this user-data root), so a developer running from
        a checkout edits the checkout's file and not the installed app's.
        """

        configured = os.environ.get("FINESUB_CONFIG_FILE", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        found = resolve_config_file()
        return found if found is not None else self.user_data / "config.toml"

    def shared_settings(self) -> SharedSettings:
        return SharedSettings(
            split_length_scale=config_float(
                "segmentation", "length_scale", path=self.config_path
            )
        )

    def save_shared_settings(self, values: SharedSettings) -> SharedSettings:
        """Write the panel's half of ``config.toml``.

        Sparse on purpose: ``None`` removes the key instead of writing the
        default out, so the file stays a record of decisions someone made and a
        default we improve later still reaches them. The writer preserves every
        other byte, comments included -- this file is hand-editable and stays
        that way.
        """

        scale = values.split_length_scale
        if scale is not None:
            # Reject here rather than at the next run: this is the only place
            # that can tell the user which value was refused and why.
            scale = validate_split_length_scale(scale)
        update_config_file(
            self.config_path,
            {"segmentation": {"length_scale": scale}},
        )
        clear_config_cache()
        return self.shared_settings()

    def public_settings(self) -> PublicSettings:
        keys = self._read_keys()
        return PublicSettings(
            api_keys={
                provider: "configured" if keys.get(env_name) else "missing"
                for provider, env_name in _ENV_NAMES.items()
            }
        )

    def build_worker_env(self) -> dict[str, str]:
        keys = self._read_keys()
        return {
            env_name: keys[env_name]
            for env_name in self._known_env_names()
            if keys.get(env_name)
        }

    def save_api_keys(
        self,
        *,
        gemini: str | None = None,
        gemini_free: str | None = None,
        gemini_paid: str | None = None,
        exa: str | None = None,
        tavily: str | None = None,
    ) -> None:
        if gemini is not None:
            if gemini_free is not None and gemini_free.strip() != gemini.strip():
                raise ValueError("gemini and gemini_free disagree")
            gemini_free = gemini
        requested: dict[Provider, str | None] = {
            "gemini_free": gemini_free,
            "gemini_paid": gemini_paid,
            "exa": exa,
            "tavily": tavily,
        }
        # Only the providers the caller actually changed are written: a value
        # that is unreadable on this machine must keep its ciphertext line
        # (it may open fine on the machine the file came from).
        updates: dict[str, str | None] = {}
        for provider, value in requested.items():
            if value is None:
                continue
            normalized = self._normalize_secret(value)
            updates[_ENV_NAMES[provider]] = normalized or None
        if updates:
            self._write_keys(updates)

    def delete_api_key(self, provider: ProviderInput) -> None:
        provider = "gemini_free" if provider == "gemini" else provider
        if provider not in _ENV_NAMES:
            raise ValueError(f"Unknown API provider: {provider}")
        self._write_keys({_ENV_NAMES[provider]: None})

    def save_provider_key(self, provider_id: str, value: str) -> None:
        env_name = self._custom_provider_env(provider_id)
        normalized = self._normalize_secret(value)
        self._write_keys({env_name: normalized or None})

    def delete_provider_key(self, provider_id: str) -> None:
        self._write_keys({self._custom_provider_env(provider_id): None})

    def reveal_api_keys(self) -> dict[str, list[dict[str, str]]]:
        """Plaintext entries per provider, for the settings panel.

        Exists because the protected values are bound to this Windows account:
        the user must be able to take their keys out *before* a machine switch
        or reinstall, and desktop users cannot be assumed to reach for the CLI.
        """

        keys = self._read_keys()
        return {
            provider: [
                {"name": label, "key": key, "masked": secrets.masked(key)}
                for label, key in secrets.iter_entries(keys.get(env_name, ""))
            ]
            for provider, env_name in _ENV_NAMES.items()
        }

    def export_api_keys(self, destination: Path) -> dict[str, object]:
        """Write a user-selected plaintext transfer file without logging values."""

        target = destination.expanduser().resolve()
        if target == self.env_path:
            raise ValueError("不能用明文导出文件覆盖 FineSub 的加密密钥文件。")
        if target.exists() and target.is_dir():
            raise ValueError("密钥导出位置必须是文件。")
        values = self._read_keys()
        if not values:
            return {"path": None, "count": 0}
        target.write_text(
            "\n".join(f"{name}={values[name]}" for name in sorted(values)) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return {"path": str(target), "count": len(values)}

    @staticmethod
    def _normalize_secret(value: str) -> str:
        normalized = value.strip()
        if "\r" in normalized or "\n" in normalized:
            raise ValueError("API keys must be a single line")
        return normalized

    def _read_keys(self) -> dict[str, str]:
        known_names = {
            *self._known_env_names(),
            *_LEGACY_ENV_NAMES.values(),
        }
        values = {
            name: value
            for name, value in secrets.read_env_file(self.env_path).items()
            if name in known_names and value
        }
        migration: dict[str, str | None] = {}
        for provider, legacy_name in _LEGACY_ENV_NAMES.items():
            current_name = _ENV_NAMES[provider]
            legacy_value = values.pop(legacy_name, "")
            if not legacy_value:
                continue
            migration[legacy_name] = None
            if not values.get(current_name):
                values[current_name] = legacy_value
                migration[current_name] = legacy_value
        if migration:
            self._write_keys(migration)
        return {
            name: values[name]
            for name in self._known_env_names()
            if values.get(name)
        }

    def _known_env_names(self) -> set[str]:
        names = set(_ENV_NAMES.values())
        try:
            from finesub.llm.routing.model_routes import default_model_routes

            names.update(
                provider.key_env
                for provider in default_model_routes().providers.values()
                if provider.key_env
            )
        except (OSError, RuntimeError, ValueError):
            pass
        return names

    @staticmethod
    def _custom_provider_env(provider_id: str) -> str:
        normalized = provider_id.strip()
        if not normalized:
            raise ValueError("provider id must not be blank")
        from finesub.llm.routing.model_routes import default_model_routes

        provider = default_model_routes().providers.get(normalized)
        if provider is None or not provider.key_env:
            raise ValueError(f"Unknown custom API provider: {normalized}")
        return provider.key_env

    # ----------------------------------------------------- model routing

    def routing_settings(self) -> RoutingSettings:
        """Project the core's public catalog into a JSON-safe desktop DTO."""

        try:
            from finesub.llm.routing.execution_policy import load_execution_settings
            from finesub.llm.routing.model_routes import (
                TASK_GROUP_IDS,
                default_model_routes,
            )

            routes = default_model_routes()
            execution = load_execution_settings()
            keys = self._read_keys()

            def preset_uses_agent(preset_id: str) -> bool:
                group_ids = set(routes.presets[preset_id].bindings.values())
                if preset_id != "default":
                    group_ids.update(routes.presets["default"].bindings.values())
                return any(
                    routes.targets[target_id].backend == "local_agent"
                    for group_id in group_ids
                    for target_id in routes.model_groups[group_id].target_ids
                )

            presets = [
                RoutingPresetSummary(
                    id=preset.id,
                    name=preset.name,
                    active=preset.id == routes.active_preset_id,
                    test_target_id=preset.test_target_id,
                    uses_local_agent=preset_uses_agent(preset.id),
                    warnings=routes.preset_binding_warnings(preset.id),
                )
                for preset in routes.presets.values()
            ]
            providers = [
                RoutingProviderSummary(
                    id=provider.id,
                    kind=provider.kind,
                    base_url=provider.base_url,
                    key_env=provider.key_env,
                    configured=bool(
                        keys.get(
                            provider.key_env
                            or _PROVIDER_TIER_ENV_NAMES.get(provider.id, "")
                        )
                    ),
                )
                for provider in routes.providers.values()
            ]
            targets = []
            for target in routes.targets.values():
                fact = routes.target_fact(target.id)
                targets.append(
                    RoutingTargetSummary(
                        id=target.id,
                        display_name=fact.display_name,
                        backend=target.backend,
                        provider_tier=fact.provider_tier,
                        api_model_id=fact.api_model_id,
                        supports_audio=fact.supports_audio,
                        supports_video=fact.supports_video,
                        supports_native_search=fact.supports_native_search,
                        is_free=fact.is_free,
                        quality_score=fact.quality_score,
                    )
                )
            return RoutingSettings(
                active_preset_id=routes.active_preset_id,
                execution_policy=execution.policy_id,
                local_agent_timeout_seconds=execution.local_agent_timeout_seconds,
                local_agent_allow_unisolated_user_config=(
                    execution.local_agent_allow_unisolated_user_config
                ),
                local_agent_service_tier=execution.local_agent_service_tier,
                local_agent_reasoning_effort=execution.local_agent_reasoning_effort,
                local_agent_max_parallel=execution.local_agent_max_parallel,
                presets=presets,
                policies=sorted(routes.policies),
                providers=providers,
                targets=targets,
                model_groups={
                    group_id: list(group.target_ids)
                    for group_id, group in routes.model_groups.items()
                    if not group_id.startswith(("target:", "preferred:"))
                },
                task_groups=list(TASK_GROUP_IDS),
                local_agent_bound=routes.binds_local_agent(),
                config_path=str(self.config_path),
            )
        except Exception as error:  # malformed hand-edited config stays recoverable
            return RoutingSettings(
                config_path=str(self.config_path),
                error=f"{type(error).__name__}: {error}",
            )

    def save_routing_settings(self, values: RoutingUpdate) -> RoutingSettings:
        from finesub.llm.routing.execution_policy import ExecutionSettings
        from finesub.llm.routing.model_routes import (
            DEFAULT_EXECUTION_POLICY,
            default_model_routes,
        )

        routes = default_model_routes()
        if values.preset not in routes.presets:
            raise ValueError(f"Unknown routing preset: {values.preset}")
        if values.execution_policy not in routes.policies:
            raise ValueError(f"Unknown execution policy: {values.execution_policy}")
        defaults = ExecutionSettings()
        update_config_file(
            self.config_path,
            {
                "llm": {
                    "preset": None if values.preset == "default" else values.preset,
                    "execution_policy": (
                        None
                        if values.execution_policy == DEFAULT_EXECUTION_POLICY
                        else values.execution_policy
                    ),
                    "local_agent_timeout_seconds": (
                        None
                        if values.local_agent_timeout_seconds
                        == defaults.local_agent_timeout_seconds
                        else values.local_agent_timeout_seconds
                    ),
                    "local_agent_allow_unisolated_user_config": (
                        None
                        if values.local_agent_allow_unisolated_user_config
                        == defaults.local_agent_allow_unisolated_user_config
                        else values.local_agent_allow_unisolated_user_config
                    ),
                    "local_agent_service_tier": (
                        None
                        if values.local_agent_service_tier
                        == defaults.local_agent_service_tier
                        else values.local_agent_service_tier
                    ),
                    "local_agent_reasoning_effort": (
                        None
                        if values.local_agent_reasoning_effort
                        == defaults.local_agent_reasoning_effort
                        else values.local_agent_reasoning_effort
                    ),
                    "local_agent_max_parallel": (
                        None
                        if values.local_agent_max_parallel
                        == defaults.local_agent_max_parallel
                        else values.local_agent_max_parallel
                    ),
                }
            },
        )
        clear_config_cache()
        default_model_routes.cache_clear()
        return self.routing_settings()

    def probe_local_agents(self) -> list[LocalAgentStatus]:
        """Probe installed CLIs only; never spend an API/subscription call."""

        from finesub.llm.routing.execution_policy import (
            driver_for_provider_tier,
            load_execution_settings,
        )
        from finesub.llm.routing.model_routes import default_model_routes

        routes = default_model_routes()
        execution = load_execution_settings()
        grouped: dict[str, dict[str, set[str]]] = {}
        first_target: dict[str, str] = {}
        for target_id, target in routes.targets.items():
            if target.backend != "local_agent":
                continue
            fact = routes.target_fact(target_id)
            row = grouped.setdefault(
                fact.provider_tier, {"models": set(), "pools": set()}
            )
            row["models"].add(fact.api_model_id)
            if fact.effective_quota_pool:
                row["pools"].add(fact.effective_quota_pool)
            first_target.setdefault(fact.provider_tier, target_id)

        statuses: list[LocalAgentStatus] = []
        for tier, row in sorted(grouped.items()):
            fact = routes.target_fact(first_target[tier])
            try:
                driver = driver_for_provider_tier(
                    execution,
                    provider_tier=tier,
                    model=fact.api_model_id,
                )
                probe = driver.probe()
                if not probe.available:
                    status = probe.failure_kind or "broken"
                    if status not in {"missing", "broken"}:
                        status = "broken"
                    detail = probe.error
                    ready = False
                elif not driver.meets_requirements(probe):
                    status = "unusable"
                    detail = "the installed CLI lacks capabilities required by FineSub"
                    ready = False
                else:
                    blocker = driver.check_environment() or ""
                    status = "unusable" if blocker else "ready"
                    detail = blocker
                    ready = not blocker
                statuses.append(
                    LocalAgentStatus(
                        provider_tier=tier,
                        driver=driver.driver_id,
                        models=sorted(row["models"]),
                        quota_pools=sorted(row["pools"]),
                        status=status,
                        available=ready,
                        version=probe.version,
                        detail=detail,
                    )
                )
            except Exception as error:
                statuses.append(
                    LocalAgentStatus(
                        provider_tier=tier,
                        models=sorted(row["models"]),
                        quota_pools=sorted(row["pools"]),
                        status="error",
                        detail=f"{type(error).__name__}: {error}",
                    )
                )
        return statuses

    def _write_keys(self, updates: dict[str, str | None]) -> None:
        # Line-preserving by contract: comments, the FINESUB_KEYRING line and
        # variables not named here survive byte for byte, and new values are
        # born encrypted (plaintext with a warning when DPAPI is unavailable).
        secrets.update_env_file(self.env_path, updates)
