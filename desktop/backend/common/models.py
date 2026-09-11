from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    model_serializer,
)


PipelineStage = Literal[
    "vocal",
    "aligned",
    "stable",
    "raw-srt",
    "translated-srt",
    "final-srt",
]

#: What class of GPU this machine has -- NOT a cap on what a run may use.
#: `auto` asks the driver, which is the default and almost always right; the
#: named tiers exist for "leave some of the card to something else". The names
#: mirror `finesub.speech.runtime.resources.GPU_TIERS`, which owns what each
#: one means.
GpuTier = Literal[
    "auto", "cpu", "entry", "standard", "standard_large_vram", "high"
]

#: Renamed 2026-08-12 (docs/llm_harness_behavior.md). Task history is shared
#: with the CLI, merged and never truncated, so every record written before
#: that rename still carries the old word -- and history is read back through
#: these models with unreadable entries *silently skipped* (jobs/history.py),
#: so rejecting them would empty a user's task list rather than fail loudly.
#: Accepted on input only; nothing writes the retired words again, so this
#: mapping can go once no such record can still be on disk.
_RETIRED_DIFFICULTY = {
    "high": "quality",
    "med": "intermediate",
    "minimum": "efficiency",
}


def _accept_retired_difficulty(value: object) -> object:
    return _RETIRED_DIFFICULTY.get(value, value) if isinstance(value, str) else value


#: The LLM layer's vocabulary (`finesub.llm.routing.profiles.DIFFICULTY`). The
#: worker passes this value straight through, so anything else raises there --
#: after ASR has already run, which is the most expensive place to find out.
#: Carrying the coercion on the alias means every model that uses it accepts
#: old history without each one remembering to add a validator.
LLMDifficulty = Annotated[
    Literal["quality", "intermediate", "efficiency"],
    BeforeValidator(_accept_retired_difficulty),
]


def _normalize_asr_decode_batch(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("ASR decode batch must be auto or a positive integer")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "auto":
            return "auto"
        try:
            value = int(normalized)
        except ValueError as error:
            raise ValueError(
                "ASR decode batch must be auto or a positive integer"
            ) from error
    if isinstance(value, int) and value >= 1:
        return value
    raise ValueError("ASR decode batch must be auto or a positive integer")


AsrDecodeBatch = Annotated[
    int | Literal["auto"], BeforeValidator(_normalize_asr_decode_batch)
]


class DesktopModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BridgeError(DesktopModel):
    code: str
    message: str
    action: str | None = None


class CapabilityState(DesktopModel):
    raw_srt: bool = True
    translation: bool = False
    web_search: bool = False


class PublicSettings(DesktopModel):
    api_keys: dict[str, Literal["configured", "missing"]]


class RoutingPresetSummary(DesktopModel):
    id: str
    name: str
    active: bool = False
    test_target_id: str = ""
    uses_local_agent: bool = False
    warnings: list[str] = Field(default_factory=list)


class RoutingProviderSummary(DesktopModel):
    id: str
    kind: str
    base_url: str = ""
    key_env: str = ""
    configured: bool = False


class RoutingTargetSummary(DesktopModel):
    id: str
    display_name: str
    backend: str
    provider_tier: str
    api_model_id: str
    supports_audio: bool = False
    supports_video: bool = False
    supports_native_search: bool = False
    is_free: bool = False
    quality_score: int = 0


class RoutingSettings(DesktopModel):
    active_preset_id: str = ""
    execution_policy: str = ""
    local_agent_timeout_seconds: int = 1680
    local_agent_allow_unisolated_user_config: bool = False
    local_agent_service_tier: Literal["", "fast", "flex"] = ""
    local_agent_reasoning_effort: Literal["", "low", "medium", "high", "xhigh"] = ""
    local_agent_max_parallel: int = 4
    presets: list[RoutingPresetSummary] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    providers: list[RoutingProviderSummary] = Field(default_factory=list)
    targets: list[RoutingTargetSummary] = Field(default_factory=list)
    model_groups: dict[str, list[str]] = Field(default_factory=dict)
    task_groups: list[str] = Field(default_factory=list)
    local_agent_bound: bool = False
    config_path: str = ""
    error: str = ""


class RoutingUpdate(DesktopModel):
    preset: str
    execution_policy: str
    local_agent_timeout_seconds: int = Field(ge=10)
    local_agent_allow_unisolated_user_config: bool = False
    local_agent_service_tier: Literal["", "fast", "flex"] = ""
    local_agent_reasoning_effort: Literal["", "low", "medium", "high", "xhigh"] = ""
    local_agent_max_parallel: int = Field(ge=1)


class LocalAgentStatus(DesktopModel):
    provider_tier: str
    driver: str = ""
    models: list[str] = Field(default_factory=list)
    quota_pools: list[str] = Field(default_factory=list)
    status: Literal["ready", "missing", "broken", "unusable", "error"]
    available: bool = False
    version: str = ""
    detail: str = ""


class TaskDefaults(BaseModel):
    """What the task form should start with, i.e. "what I picked last time".

    A subset of ``TaskRequest``, every field optional: absent means follow the
    code default, which is what lets a default still be improved later. Unknown
    fields are ignored rather than rejected -- this is program-written state,
    and a key left over from another version is not something a user can fix.

    ``split_length_scale`` is deliberately absent: it is a shared setting that
    the CLI reads too, so it lives in ``config.toml``. One key, one home.
    """

    model_config = ConfigDict(extra="ignore")

    model_name: str | None = None
    device: Literal["cuda", "cpu"] | None = None
    gpu_index: int | None = None
    gpu_name: str | None = None
    language: str | None = None
    gpu_tier: GpuTier | None = None
    gap_sec: float | None = Field(default=None, ge=0)
    separator_sample_rate: Literal[44100, 32000, 22050] | None = None
    separate: bool | None = None
    vad_silero_assist: bool | None = None
    qwen_verify: Literal["auto", "on", "off"] | None = None
    lang_redecode: Literal["auto", "on", "off"] | None = None
    asr_decode_batch: AsrDecodeBatch | None = None
    asr_context: Literal["off", "terms", "full"] | None = None
    word: bool | None = None
    asr_stabilize_profile: Literal[-1, 0, 1, 2] | None = None
    stage: PipelineStage | None = None
    llm_media: Literal["text", "audio", "video"] | None = None
    llm_correction_media: Literal["", "text", "audio", "video"] | None = None
    llm_planning_media: Literal["", "text", "audio", "video"] | None = None
    llm_retrieval: Literal["none", "local", "native"] | None = None
    llm_difficulty: LLMDifficulty | None = None
    llm_continuity: Literal["serial", "parallel"] | None = None
    llm_parallel_windows: int | None = Field(default=None, ge=1)
    llm_fast: Literal["auto", "on", "off"] | None = None
    llm_output_scale: float | None = Field(default=None, gt=0)
    llm_model: list[str] | None = None
    style: str | None = None
    style_mode: Literal["none", "read", "update"] | None = None
    download_video_source: bool | None = None
    knowledge: Literal["none", "collect", "update"] | None = None
    postprocess_profile: Literal[-1, 0, 1, 2, 3, 4] | None = None
    max_retries_per_window: int | None = Field(default=None, ge=0)
    max_replacements_per_window: int | None = Field(default=None, ge=0)
    resume: bool | None = None
    cleanup_intermediate: bool | None = None

    @model_serializer
    def _sparse(self) -> dict[str, object]:
        """Serialize the chosen fields only -- never an unset one as null.

        The front end spreads this object straight over the task request, so a
        `model_name: null` on the wire does not mean "unset", it *overwrites* a
        real default and the request stops validating. Doing it here rather
        than at each dump site is the point: every path out of the process
        (bootstrap payload, get_preferences, the file itself) is sparse by
        construction and no caller can forget the flag.
        """

        return {key: value for key, value in self.__dict__.items() if value is not None}


class Preferences(DesktopModel):
    """The front end's own persisted state.

    ``ui`` is stored verbatim: it is the renderer's business (theme, language,
    dismissed dialogs), and validating every new toggle here would be a schema
    treadmill for values the backend never interprets. ``task_defaults`` is
    validated, because it ends up as pipeline arguments.
    """

    ui: dict[str, object] = Field(default_factory=dict)
    task_defaults: TaskDefaults = Field(default_factory=TaskDefaults)


class SharedSettings(DesktopModel):
    """The half of the settings panel that writes ``config.toml``.

    ``None`` means "not set" -- the key is removed from the file and the code
    default applies again, which is also what keeps the file readable by hand.
    """

    split_length_scale: float | None = None


class ResourceInstallSnapshot(DesktopModel):
    resource_id: str
    resource_version: str
    state: Literal["queued", "running", "paused", "ready", "failed"]
    phase: Literal[
        "waiting",
        "downloading",
        "verifying",
        "extracting",
        "installing_python",
        "creating_environment",
        "installing_dependencies",
        "activating",
        "complete",
    ] = "waiting"
    message: str = ""
    downloaded: int = 0
    total: int = 0
    bytes_per_second: float = 0
    cache_path: str
    install_path: str
    logs: list[str] = Field(default_factory=list)
    # The full transcript on disk; `logs` above is only its tail.
    log_path: str = ""
    error: str = ""
    started_at: float
    updated_at: float


class UpdateInstallSnapshot(DesktopModel):
    version: str
    kind: Literal["app", "full"]
    state: Literal["queued", "running", "ready", "failed"]
    phase: Literal["waiting", "downloading", "installing", "complete"] = "waiting"
    message: str = ""
    downloaded: int = 0
    total: int = 0
    bytes_per_second: float = 0
    # An "app" update swaps the version pointer, so the running launcher keeps
    # its process and only needs a restart. A "full" update hands control to an
    # external updater that replaces this install, so Yanami Sub has to exit for it
    # to proceed -- a different ask of the user, hence two flags rather than one.
    restart_required: bool = False
    exit_required: bool = False
    error: str = ""
    started_at: float
    updated_at: float


class TaskRequest(DesktopModel):
    input: str
    output: str | None = None
    # The CLI's --name: a bare stem that becomes out/<name>/<name>.srt. It names
    # a directory, so a separator would escape the tree -- hence the validator.
    # Blank keeps the derived name (source filename or video id).
    name: str = ""
    # Off by default: the run directory is what makes a rerun cheap (the
    # pipeline skips stages whose outputs exist) and what a later LLM pass reads.
    cleanup_intermediate: bool = False
    stage: PipelineStage = "raw-srt"
    model_name: str = "large-v3-turbo"
    # `None` = "not chosen", which is a different statement from "cuda" and has
    # to stay expressible: `--gpu-tier cpu` plus an explicit `--device cuda` is
    # a contradiction the CLI refuses, and a front end that always sends a
    # device would silently obey one half of it instead. The backend signature
    # supplies the default (README_DEV -> 开发原则: no second copy of it here).
    device: Literal["cuda", "cpu"] | None = None
    # Which CUDA card to use, when the machine has more than one. None lets
    # CUDA pick, which is what every single-GPU machine wants.
    gpu_index: int | None = None
    # The card that index meant when it was chosen. Indexes are positions, not
    # identities: swap the card in that slot and the index still resolves, so
    # without the name nothing would notice the task running on hardware the
    # user never picked.
    gpu_name: str = ""
    language: str | None = None
    # `auto` = ask the card. A tier names what CLASS of card this is, not a
    # cap on what a run may use, so the backend resolves it from the driver.
    gpu_tier: GpuTier = "auto"
    gap_sec: float = Field(default=0.3, ge=0)
    separator_sample_rate: Literal[44100, 32000, 22050] | None = None
    # None follows config.toml; False still produces the normalized vocal
    # artifact, but treats the input as an already-clean voice track.
    separate: bool | None = None
    vad_silero_assist: bool | None = None
    qwen_verify: Literal["auto", "on", "off"] = "auto"
    lang_redecode: Literal["auto", "on", "off"] = "auto"
    asr_decode_batch: AsrDecodeBatch = "auto"
    asr_context: Literal["off", "terms", "full"] = "off"
    word: bool = False
    asr_stabilize_profile: Literal[-1, 0, 1, 2] = 0
    # None = follow config.toml, then the calibrated default. Set per task only
    # to override the shared setting for this one run.
    split_length_scale: float | None = Field(default=None, ge=0.6, le=1.6)
    # Orthogonal switch axes (docs/llm_harness_behavior.md); the old
    # llm_route/llm_level presets and enable_web_search retired with them.
    llm_media: Literal["text", "audio", "video"] = "audio"
    # Empty means inherit llm_media, exactly like the core CLI.
    llm_correction_media: Literal["", "text", "audio", "video"] = ""
    llm_planning_media: Literal["", "text", "audio", "video"] = ""
    llm_retrieval: Literal["none", "local", "native"] = "local"
    llm_difficulty: LLMDifficulty = "quality"
    llm_continuity: Literal["serial", "parallel"] = "serial"
    llm_parallel_windows: int = Field(default=1, ge=1)
    llm_fast: Literal["auto", "on", "off"] = "auto"
    llm_output_scale: float = Field(default=1.0, gt=0)
    # Repeatable core ``--llm-model`` values. A bare id overrides every task
    # group; ``correction-text=...`` pins one group for this run only.
    llm_model: list[str] = Field(default_factory=list)
    llm_video: str | None = None
    extra_info: str = ""
    extra_style: str = ""
    task_summary: str = ""
    style: str | None = None
    style_mode: Literal["none", "read", "update"] | None = None
    download_video_source: bool = True
    # Default on: the knowledge base is what makes later tasks better, and it
    # only runs when the LLM stage does -- a plain transcription ignores it.
    knowledge: Literal["none", "collect", "update"] = "update"
    refined_srt: str | None = None
    postprocess_profile: Literal[-1, 0, 1, 2, 3, 4] = 0
    max_retries_per_window: int = Field(default=5, ge=0)
    max_replacements_per_window: int = Field(default=1, ge=0)
    resume: bool = True

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("input must not be blank")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            return ""
        if "/" in normalized or "\\" in normalized or normalized in {".", ".."}:
            raise ValueError("输出名称不能包含路径分隔符")
        return normalized

    @field_validator("language", mode="before")
    @classmethod
    def normalize_language(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("llm_video", "style", "refined_srt", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("llm_model", mode="before")
    @classmethod
    def normalize_llm_model(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.splitlines()
        if not isinstance(value, (list, tuple)):
            raise ValueError("LLM model overrides must be a list of strings")
        normalized = [str(item).strip() for item in value if str(item).strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("LLM model overrides must not contain duplicate rows")
        return normalized

    @field_validator("llm_model")
    @classmethod
    def validate_llm_model(cls, value: list[str]) -> list[str]:
        if not value:
            return value
        from finesub.llm.routing.model_routes import (
            TASK_GROUP_IDS,
            default_model_routes,
            parse_llm_model_args,
        )

        overlay = parse_llm_model_args(value)
        unknown_groups = sorted(set(overlay) - {"default", *TASK_GROUP_IDS})
        if unknown_groups:
            raise ValueError(
                "unknown LLM task group(s): " + ", ".join(unknown_groups)
            )
        routes = default_model_routes()
        known = set(routes.model_groups) | set(routes.targets)
        unknown_values = sorted(set(overlay.values()) - known)
        if unknown_values:
            raise ValueError(
                "unknown LLM model group or target(s): " + ", ".join(unknown_values)
            )
        return value


class KnowledgeCommandRequest(DesktopModel):
    command: Literal[
        "log",
        "show",
        "edit",
        "new",
        "retire",
        "revert",
        "restore",
        "refresh",
        "phase-b",
        "candidates",
        "verify",
        "repair",
        "ingest",
    ]
    args: list[str] = Field(default_factory=list, max_length=64)
    content: str = Field(default="", max_length=2_000_000)

    @field_validator("args")
    @classmethod
    def validate_args(cls, value: list[str]) -> list[str]:
        normalized = [str(item) for item in value]
        if any("\x00" in item or len(item) > 16_384 for item in normalized):
            raise ValueError("knowledge command argument is invalid")
        return normalized


class KnowledgeShareCommandRequest(DesktopModel):
    command: Literal[
        "register",
        "mark",
        "unmark",
        "push",
        "status",
        "pull",
        "conflicts",
        "review",
    ]
    args: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("args")
    @classmethod
    def validate_args(cls, value: list[str]) -> list[str]:
        return KnowledgeCommandRequest.validate_args(value)


class RefinedKnowledgeUpdateRequest(DesktopModel):
    task_id: str = Field(min_length=1, max_length=200)
    refined_srt: str = Field(min_length=1, max_length=32_768)
    task_summary: str = Field(default="", max_length=20_000)
    llm_model: list[str] = Field(default_factory=list)
    apply: bool = True
    resume: bool = True

    @field_validator("task_id", "refined_srt")
    @classmethod
    def strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("llm_model", mode="before")
    @classmethod
    def normalize_llm_model(cls, value: object) -> object:
        return TaskRequest.normalize_llm_model(value)

    @field_validator("llm_model")
    @classmethod
    def validate_llm_model(cls, value: list[str]) -> list[str]:
        return TaskRequest.validate_llm_model(value)


class BatchItemRequest(TaskRequest):
    """One independently isolated item in a core scheduler run."""

    group: str = ""
    priority: int = 0

    @field_validator("group")
    @classmethod
    def normalize_group(cls, value: str) -> str:
        return value.strip()


class BatchWorkers(DesktopModel):
    download: int = Field(default=2, ge=1, le=8)
    asr: int = Field(default=1, ge=1, le=4)
    llm: int = Field(default=2, ge=1, le=8)


class BatchRequest(DesktopModel):
    items: list[BatchItemRequest] = Field(min_length=1, max_length=500)
    workers: BatchWorkers = Field(default_factory=BatchWorkers)
    asr_queue_size: int = Field(default=4, ge=1, le=32)
    retry_failed: int = Field(default=1, ge=0, le=10)

    @model_validator(mode="after")
    def unique_sources(self) -> "BatchRequest":
        seen: set[str] = set()
        devices: set[tuple[str | None, int | None, str]] = set()
        model_routes: set[tuple[str, ...]] = set()
        for item in self.items:
            source = item.input.casefold()
            if source in seen:
                raise ValueError(f"batch source is listed twice: {item.input}")
            seen.add(source)
            devices.add((item.device, item.gpu_index, item.gpu_name))
            model_routes.add(tuple(item.llm_model))
        if len(devices) > 1:
            raise ValueError("all items in one batch must use the same processing device")
        if len(model_routes) > 1:
            raise ValueError("all items in one batch must use the same LLM model overrides")
        return self


class BatchItemSnapshot(DesktopModel):
    index: int
    input: str
    label: str
    state: Literal[
        "queued", "running", "done", "failed", "skipped", "dropped"
    ] = "queued"
    stage: str = ""
    error: str = ""
    outputs: dict[str, str] = Field(default_factory=dict)


class BatchSnapshot(DesktopModel):
    batch_id: str
    state: Literal[
        "running", "completed", "failed", "cancelled", "interrupted"
    ]
    request: BatchRequest
    items: list[BatchItemSnapshot]
    created_at: float
    updated_at: float
    error: str = ""
    log_path: str = ""
    status_path: str = ""
