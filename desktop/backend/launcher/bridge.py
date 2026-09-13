from __future__ import annotations

from collections.abc import Callable
import logging
import os
from pathlib import Path
import webbrowser
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from desktop.backend.batches.manager import BatchAlreadyRunning, BatchNotFound
from desktop.backend.common.models import (
    BatchRequest,
    BridgeError,
    KnowledgeCommandRequest,
    KnowledgeShareCommandRequest,
    RefinedKnowledgeUpdateRequest,
    RoutingUpdate,
    SharedSettings,
    TaskRequest,
)
from desktop.backend.knowledge import KnowledgeOperationError, KnowledgeService
from desktop.backend.jobs.launch import WorkerLaunchContext
from desktop.backend.jobs.manager import JobAlreadyRunning, JobNotFound
from desktop.backend.settings.preferences import PreferencesStore
from desktop.backend.settings.store import SettingsStore


LOGGER = logging.getLogger(__name__)


class ApiKeyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gemini: str | None = None
    gemini_free: str | None = None
    gemini_paid: str | None = None
    exa: str | None = None
    tavily: str | None = None


class PreferencesPatch(BaseModel):
    """A partial update: only the sections present are touched.

    Inside a section, a null value resets that one setting rather than writing
    a default -- absent stays absent, which is what keeps the store sparse.
    """

    model_config = ConfigDict(extra="forbid")

    ui: dict[str, Any] | None = None
    task_defaults: dict[str, Any] | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _success(value: Any = None) -> dict[str, Any]:
    return {"ok": True, "data": _json_safe(value)}


def _failure(error: BridgeError) -> dict[str, Any]:
    return {"ok": False, "error": error.model_dump(mode="json")}


RESOURCE_LABELS = {
    "uv": "Python 运行环境",
    "ffmpeg": "FFmpeg",
    "git": "git（知识库更新需要）",
    "yt-dlp": "yt-dlp（链接下载需要）",
}


def _missing_resource_error(missing: list[str], verb: str) -> BridgeError:
    names = "、".join(RESOURCE_LABELS.get(item, item) for item in missing)
    return BridgeError(
        code="runtime_required",
        message=f"请先安装 {names}，再{verb}字幕任务。",
        action="open_resources",
    )


class DesktopBridge:
    def __init__(
        self,
        *,
        jobs: Any,
        resources: Any,
        resource_installs: Any | None = None,
        settings: SettingsStore,
        batches: Any | None = None,
        preferences: PreferencesStore | None = None,
        updates: Any | None = None,
        update_installs: Any | None = None,
        file_selector: Callable[[], str | None] | None = None,
        batch_file_selector: Callable[[], list[str]] | None = None,
        batch_manifest_selector: Callable[[], str | None] | None = None,
        batch_manifest_export_selector: Callable[[], str | None] | None = None,
        directory_selector: Callable[[], str | None] | None = None,
        key_export_selector: Callable[[], str | None] | None = None,
        knowledge: Any | None = None,
        output_opener: Callable[[Path], None] | None = None,
        url_opener: Callable[[str], Any] | None = None,
        window: Any | None = None,
        tray: Any | None = None,
        relauncher: Callable[[], Any] | None = None,
        app_version: str = "development",
    ) -> None:
        self.jobs = jobs
        self.batches = batches
        self.resources = resources
        self.resource_installs = resource_installs
        self.settings = settings
        self.preferences = preferences or PreferencesStore(settings.user_data)
        self.updates = updates
        self.update_installs = update_installs
        self.file_selector = file_selector
        self.batch_file_selector = batch_file_selector
        self.batch_manifest_selector = batch_manifest_selector
        self.batch_manifest_export_selector = batch_manifest_export_selector
        self.directory_selector = directory_selector
        self.key_export_selector = key_export_selector
        self.knowledge = knowledge or KnowledgeService(
            settings.user_data / "knowledge",
            lambda: self.jobs.worker_context,
        )
        self.output_opener = output_opener or self._open_in_explorer
        self.url_opener = url_opener or webbrowser.open
        self.window = window
        self.tray = tray
        self.relauncher = relauncher
        self.app_version = app_version

    def get_bootstrap_state(self) -> dict[str, Any]:
        return self._guard(
            lambda: {
                "app_version": self.app_version,
                "resources": self.resources.check_all(),
                "resource_installs": (
                    self.resource_installs.list()
                    if self.resource_installs is not None
                    else []
                ),
                "capabilities": self.settings.get_capabilities(),
                "settings": self.settings.public_settings(),
                "routing": self.settings.routing_settings(),
                "preferences": self.preferences.load(),
                "shared_settings": self.settings.shared_settings(),
                "config_path": str(self.settings.config_path),
                "storage": self._storage_state(),
                "gpus": self._gpu_snapshot(),
                "task": self.jobs.snapshot(),
                "tasks": self.jobs.history(),
                "batch": self.batches.snapshot() if self.batches is not None else None,
                "batches": self.batches.history() if self.batches is not None else [],
            }
        )

    def _gpu_snapshot(self) -> dict[str, Any]:
        probe = getattr(self.resources, "gpu_probe", None)
        if probe is None:
            return {"state": "unavailable", "devices": []}
        # Whatever the background probe has right now. Never waits: the state
        # is "scanning" until it answers, and the interface polls anyway.
        return probe.snapshot().to_dict()

    def _storage_state(self) -> dict[str, Any]:
        read = getattr(self.resources, "storage_state", None)
        if callable(read):
            return dict(read())
        return {
            "big_data": "",
            "default_big_data": "",
            "runtime": "",
            "models": "",
            "cache": "",
            "tasks": "",
            "agent_capsules": "",
            "relocated": False,
        }

    def rescan_gpus(self) -> dict[str, Any]:
        """Look for GPUs again -- for after a card or driver change."""

        def rescan() -> dict[str, Any]:
            probe = getattr(self.resources, "gpu_probe", None)
            if probe is None:
                raise ValueError("当前构建不支持显卡检测。")
            probe.start()
            return probe.snapshot().to_dict()

        return self._guard(rescan)

    def get_diagnostics(self) -> dict[str, Any]:
        """Run the explicit runtime probe and return one structured report."""

        def diagnose() -> dict[str, Any]:
            report = dict(self.resources.diagnostics())
            report.update(
                {
                    "app_version": self.app_version,
                    "capabilities": self.settings.get_capabilities(),
                    "gpu": self._gpu_snapshot(),
                    "active_task": self.jobs.snapshot(),
                    "active_batch": (
                        self.batches.snapshot() if self.batches is not None else None
                    ),
                }
            )
            return report

        return self._guard(diagnose)

    def select_input_file(self) -> dict[str, Any]:
        if self.file_selector is None:
            return _failure(
                BridgeError(
                    code="dialog_unavailable",
                    message="当前窗口无法打开文件选择器。",
                )
            )
        return self._guard(lambda: {"path": self.file_selector()})

    def select_batch_files(self) -> dict[str, Any]:
        if self.batch_file_selector is None:
            return _failure(
                BridgeError(
                    code="dialog_unavailable",
                    message="当前窗口无法打开多文件选择器。",
                )
            )
        return self._guard(lambda: {"paths": self.batch_file_selector()})

    def import_batch_manifest(self) -> dict[str, Any]:
        if self.batches is None or self.batch_manifest_selector is None:
            return _failure(
                BridgeError(
                    code="dialog_unavailable",
                    message="当前窗口无法打开批次清单。",
                )
            )

        def import_manifest() -> dict[str, Any]:
            selected = self.batch_manifest_selector()
            if not selected:
                return {
                    "cancelled": True,
                    "path": None,
                    "request": None,
                    "ignored_fields": [],
                }
            request, ignored = self.batches.import_manifest(Path(selected))
            return {
                "cancelled": False,
                "path": str(Path(selected).expanduser().resolve()),
                "request": request,
                "ignored_fields": ignored,
            }

        return self._guard(import_manifest)

    def export_batch_manifest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.batches is None or self.batch_manifest_export_selector is None:
            return _failure(
                BridgeError(
                    code="dialog_unavailable",
                    message="当前窗口无法导出批次清单。",
                )
            )
        try:
            request = BatchRequest.model_validate(payload)
        except ValidationError as error:
            return _failure(
                BridgeError(
                    code="invalid_request",
                    message="批次清单参数无效。",
                    action=str(error.errors(include_url=False)),
                )
            )

        def export_manifest() -> dict[str, Any]:
            selected = self.batch_manifest_export_selector()
            if not selected:
                return {"cancelled": True, "path": None, "count": 0}
            return {
                "cancelled": False,
                **self.batches.export_manifest(Path(selected), request),
            }

        return self._guard(export_manifest)

    def start_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = TaskRequest.model_validate(payload)
        except ValidationError as error:
            return _failure(
                BridgeError(
                    code="invalid_request",
                    message="任务参数无效。",
                    action=str(error.errors(include_url=False)),
                )
            )
        capability_error = self.settings.validate_request(request)
        if capability_error is not None:
            return _failure(capability_error)
        if self.batches is not None and self.batches.is_running():
            return _failure(
                BridgeError(
                    code="batch_already_running",
                    message="已有批处理正在运行。",
                    action="show_batch",
                )
            )
        missing = self._missing_resources(request)
        if missing:
            return _failure(_missing_resource_error(missing, "开始"))
        try:
            return _success(self.jobs.start(request))
        except JobAlreadyRunning:
            return _failure(
                BridgeError(
                    code="task_already_running",
                    message="已有字幕任务正在运行。",
                    action="show_current_task",
                )
            )
        except Exception:
            return self._internal_error("start_task")

    def start_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.batches is None:
            return _failure(
                BridgeError(code="batch_unavailable", message="当前构建不支持批处理。")
            )
        try:
            request = BatchRequest.model_validate(payload)
        except ValidationError as error:
            return _failure(
                BridgeError(
                    code="invalid_request",
                    message="批处理参数无效。",
                    action=str(error.errors(include_url=False)),
                )
            )
        active = self.jobs.snapshot()
        if active is not None and active.state == "running":
            return _failure(
                BridgeError(
                    code="task_already_running",
                    message="已有字幕任务正在运行。",
                    action="show_current_task",
                )
            )
        for item in request.items:
            capability_error = self.settings.validate_request(item)
            if capability_error is not None:
                return _failure(capability_error)
        missing = self._missing_batch_resources(request)
        if missing:
            return _failure(_missing_resource_error(missing, "开始"))
        try:
            return _success(self.batches.start(request))
        except BatchAlreadyRunning:
            return _failure(
                BridgeError(
                    code="batch_already_running",
                    message="已有批处理正在运行。",
                    action="show_batch",
                )
            )
        except Exception:
            return self._internal_error("start_batch")

    def cancel_batch(self, batch_id: str) -> dict[str, Any]:
        if self.batches is None:
            return _failure(
                BridgeError(code="batch_unavailable", message="当前构建不支持批处理。")
            )
        try:
            return _success(self.batches.cancel(batch_id))
        except BatchNotFound:
            return _failure(
                BridgeError(code="batch_not_found", message="没有找到该批次。")
            )
        except Exception:
            return self._internal_error("cancel_batch")

    def resume_batch(self, batch_id: str) -> dict[str, Any]:
        if self.batches is None:
            return _failure(
                BridgeError(code="batch_unavailable", message="当前构建不支持批处理。")
            )
        active = self.jobs.snapshot()
        if active is not None and active.state == "running":
            return _failure(
                BridgeError(
                    code="task_already_running",
                    message="已有字幕任务正在运行。",
                    action="show_current_task",
                )
            )
        try:
            request = self.batches.request_for(batch_id)
            for item in request.items:
                capability_error = self.settings.validate_request(item)
                if capability_error is not None:
                    return _failure(capability_error)
            missing = self._missing_batch_resources(request)
            if missing:
                return _failure(_missing_resource_error(missing, "继续"))
            return _success(self.batches.resume(batch_id))
        except BatchNotFound:
            return _failure(
                BridgeError(code="batch_not_found", message="没有找到该批次。")
            )
        except BatchAlreadyRunning:
            return _failure(
                BridgeError(
                    code="batch_already_running",
                    message="已有批处理正在运行。",
                    action="show_batch",
                )
            )
        except ValueError as error:
            return _failure(BridgeError(code="batch_not_resumable", message=str(error)))
        except Exception:
            return self._internal_error("resume_batch")

    def get_batch_snapshot(self) -> dict[str, Any]:
        return self._guard(
            self.batches.snapshot if self.batches is not None else lambda: None
        )

    def list_batches(self) -> dict[str, Any]:
        return self._guard(
            self.batches.history if self.batches is not None else lambda: []
        )

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        try:
            return _success(self.jobs.cancel(task_id))
        except JobNotFound:
            return _failure(
                BridgeError(code="task_not_found", message="没有找到该任务。")
            )
        except Exception:
            return self._internal_error("cancel_task")

    def retry_task(self, task_id: str) -> dict[str, Any]:
        try:
            validation = self._validate_saved_task(task_id)
            if validation is not None:
                return _failure(validation)
            return _success(self.jobs.retry(task_id))
        except JobNotFound:
            return _failure(
                BridgeError(code="task_not_found", message="没有找到该任务。")
            )
        except JobAlreadyRunning:
            return _failure(
                BridgeError(
                    code="task_already_running",
                    message="已有字幕任务正在运行。",
                    action="show_current_task",
                )
            )
        except Exception:
            return self._internal_error("retry_task")

    def resume_task(self, task_id: str) -> dict[str, Any]:
        try:
            validation = self._validate_saved_task(task_id)
            if validation is not None:
                return _failure(validation)
            return _success(self.jobs.resume(task_id))
        except JobNotFound:
            return _failure(
                BridgeError(code="task_not_found", message="没有找到该任务。")
            )
        except JobAlreadyRunning:
            return _failure(
                BridgeError(
                    code="task_already_running",
                    message="已有字幕任务正在运行。",
                    action="show_current_task",
                )
            )
        except ValueError as error:
            return _failure(
                BridgeError(code="task_not_resumable", message=str(error))
            )
        except Exception:
            return self._internal_error("resume_task")

    def delete_task_intermediates(self, task_id: str) -> dict[str, Any]:
        try:
            return _success(self.jobs.delete_intermediates(task_id))
        except JobNotFound:
            return _failure(
                BridgeError(code="task_not_found", message="没有找到该任务。")
            )
        except JobAlreadyRunning:
            return _failure(
                BridgeError(
                    code="task_already_running",
                    message="这个任务正在运行，先等它跑完。",
                    action="show_current_task",
                )
            )
        except ValueError as error:
            return _failure(
                BridgeError(code="task_not_cleanable", message=str(error))
            )
        except Exception:
            return self._internal_error("delete_task_intermediates")

    def get_task_snapshot(self) -> dict[str, Any]:
        return self._guard(self.jobs.snapshot)

    def list_tasks(self) -> dict[str, Any]:
        return self._guard(self.jobs.history)

    def _validate_saved_task(self, task_id: str) -> BridgeError | None:
        request = self.jobs.request_for(task_id)
        capability_error = self.settings.validate_request(request)
        if capability_error is not None:
            return capability_error
        missing = self._missing_resources(request)
        if missing:
            return _missing_resource_error(missing, "继续")
        return None

    def _missing_resources(self, request) -> list[str]:
        """What this specific request still needs.

        Requirements depend on the request: git only for a knowledge update,
        yt-dlp only for a URL. A blanket check would make every user install
        both before their first plain transcription.
        """

        ensure = getattr(self.resources, "ensure", None)
        if not callable(ensure):
            return []
        from desktop.backend.resources.desktop_service import (
            ALWAYS_REQUIRED,
            capability_requirements,
        )

        return ensure(ALWAYS_REQUIRED + capability_requirements(request))

    def _missing_batch_resources(self, request: BatchRequest) -> list[str]:
        ensure = getattr(self.resources, "ensure", None)
        if not callable(ensure):
            return []
        from desktop.backend.resources.desktop_service import (
            ALWAYS_REQUIRED,
            capability_requirements,
        )

        required = list(ALWAYS_REQUIRED)
        for item in request.items:
            for resource_id in capability_requirements(item):
                if resource_id not in required:
                    required.append(resource_id)
        return ensure(tuple(required))

    def poll_events(self, after_cursor: int = 0) -> dict[str, Any]:
        def collect() -> dict[str, Any]:
            events, next_cursor = self.jobs.events_after(after_cursor)
            return {
                "events": events,
                "nextCursor": next_cursor,
            }

        return self._guard(collect)

    def install_resource(self, resource_id: str) -> dict[str, Any]:
        if self.resource_installs is None:
            def install_legacy() -> Any:
                result = self.resources.install(resource_id, lambda event: None)
                self._refresh_worker_environment()
                return result

            return self._guard(install_legacy)
        return self._guard(lambda: self.resource_installs.start(resource_id))

    def get_resource_install(self, resource_id: str) -> dict[str, Any]:
        if self.resource_installs is None:
            return _success(None)
        return self._guard(lambda: self.resource_installs.get(resource_id))

    def list_resource_installs(self) -> dict[str, Any]:
        if self.resource_installs is None:
            return _success([])
        return self._guard(self.resource_installs.list)

    def get_resource_statuses(self) -> dict[str, Any]:
        """Refresh the authoritative resource catalog after background work."""

        return self._guard(self.resources.check_all)

    def pause_resource_install(self, resource_id: str) -> dict[str, Any]:
        if self.resource_installs is None:
            return _failure(
                BridgeError(
                    code="resource_manager_unavailable",
                    message="当前构建不支持后台资源任务。",
                )
            )
        return self._guard(lambda: self.resource_installs.pause(resource_id))

    def open_resource_location(
        self,
        resource_id: str,
        kind: Literal["cache", "install"],
    ) -> dict[str, Any]:
        if self.resource_installs is None:
            return _failure(
                BridgeError(
                    code="resource_manager_unavailable",
                    message="当前构建不支持资源目录定位。",
                )
            )

        def open_location() -> dict[str, str]:
            path = self.resource_installs.location(resource_id, kind)
            self.output_opener(path)
            return {"path": str(path)}

        return self._guard(open_location)

    def relocate_data(self, reset: bool = False) -> dict[str, Any]:
        """Choose and move the core big-data store; paths never come from JS."""

        if not isinstance(reset, bool):
            return _failure(
                BridgeError(code="invalid_request", message="目录重置参数无效。")
            )
        busy = self._storage_maintenance_blocker()
        if busy is not None:
            return _failure(busy)
        if not reset and self.directory_selector is None:
            return _failure(
                BridgeError(
                    code="dialog_unavailable",
                    message="当前窗口无法打开目录选择器。",
                )
            )
        try:
            destination = None if reset else self.directory_selector()
            if not reset and not destination:
                return _success({"cancelled": True, "storage": self._storage_state()})
            result = self.resources.relocate_big_data(
                None if reset else Path(destination),
                reset=reset,
            )
            self._after_storage_change()
            return _success({"cancelled": False, **result})
        except (ValueError, RuntimeError, OSError) as error:
            return _failure(
                BridgeError(code="storage_maintenance_failed", message=str(error))
            )
        except Exception:
            return self._internal_error("relocate_data")

    def purge_rebuildable_data(self, confirmation: str) -> dict[str, Any]:
        """Remove only data the core can recreate; tasks and settings survive."""

        if confirmation != "PURGE_REBUILDABLE_DATA":
            return _failure(
                BridgeError(code="confirmation_required", message="需要确认后才能清理。")
            )
        busy = self._storage_maintenance_blocker()
        if busy is not None:
            return _failure(busy)
        try:
            result = self.resources.purge_rebuildable_data()
            self._forget_resource_install_snapshots()
            return _success({"cancelled": False, **result})
        except (ValueError, RuntimeError, OSError) as error:
            return _failure(
                BridgeError(code="storage_maintenance_failed", message=str(error))
            )
        except Exception:
            return self._internal_error("purge_rebuildable_data")

    def get_preferences(self) -> dict[str, Any]:
        """Front-end state plus the shared settings the panel can write.

        Two stores, one call: `preferences` is this app's own memory
        (settings.json), `shared` is the slice of config.toml the CLI reads too.
        `config_path` is shown in the panel -- the file is meant to be editable
        by hand, which is only true if the user can find it.
        """

        return self._guard(
            lambda: {
                "preferences": self.preferences.load(),
                "shared": self.settings.shared_settings(),
                "config_path": str(self.settings.config_path),
            }
        )

    def save_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            values = PreferencesPatch.model_validate(payload)
            saved = self.preferences.save(
                ui=values.ui,
                task_defaults=values.task_defaults,
            )
            return _success({"preferences": saved})
        except (ValidationError, ValueError):
            return _failure(
                BridgeError(code="invalid_preferences", message="设置无效。")
            )
        except Exception:
            return self._internal_error("save_preferences")

    def save_shared_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Write config.toml. Absent/null keys are removed, not defaulted."""

        try:
            values = SharedSettings.model_validate(payload)
            saved = self.settings.save_shared_settings(values)
            # The worker is told where config.toml is through its environment,
            # and that override is only filled in when the file already exists
            # -- computed once at startup. Without this refresh, the first ever
            # write lands in a file the next task's worker does not consult,
            # and the panel's setting silently does nothing until a restart.
            self._refresh_worker_environment()
            return _success(
                {"shared": saved, "config_path": str(self.settings.config_path)}
            )
        except ValidationError:
            return _failure(
                BridgeError(code="invalid_settings", message="设置值无效。")
            )
        except ValueError as error:
            # The range check and the writer's read-back both land here, and
            # both have something specific to tell the user.
            return _failure(
                BridgeError(code="invalid_settings", message=str(error))
            )
        except Exception:
            return self._internal_error("save_shared_settings")

    def save_api_keys(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            values = ApiKeyPayload.model_validate(payload)
            self.settings.save_api_keys(**values.model_dump())
            self._refresh_worker_environment()
            return _success(self.settings.public_settings())
        except (ValidationError, ValueError):
            return _failure(
                BridgeError(
                    code="invalid_api_keys",
                    message="API Key 配置无效。",
                    action="check_api_key_values",
                )
            )
        except Exception:
            return self._internal_error("save_api_keys")

    def delete_api_key(
        self,
        provider: Literal[
            "gemini", "gemini_free", "gemini_paid", "exa", "tavily"
        ],
    ) -> dict[str, Any]:
        try:
            self.settings.delete_api_key(provider)
            self._refresh_worker_environment()
            return _success(self.settings.public_settings())
        except ValueError:
            return _failure(
                BridgeError(
                    code="invalid_provider",
                    message="未知的 API 服务商。",
                )
            )
        except Exception:
            return self._internal_error("delete_api_key")

    def reveal_api_keys(self) -> dict[str, Any]:
        # The payload is plaintext key material headed for the UI; nothing on
        # this path logs it (_internal_error records only the operation name).
        return self._guard(self.settings.reveal_api_keys)

    def export_api_keys(self) -> dict[str, Any]:
        if self.key_export_selector is None:
            return _failure(
                BridgeError(
                    code="dialog_unavailable",
                    message="当前窗口无法打开密钥导出对话框。",
                )
            )

        def export() -> dict[str, Any]:
            destination = self.key_export_selector()
            if not destination:
                return {"cancelled": True, "path": None, "count": 0}
            result = self.settings.export_api_keys(Path(destination))
            return {"cancelled": False, **result}

        return self._guard(export)

    def save_provider_key(self, provider_id: str, value: str) -> dict[str, Any]:
        try:
            self.settings.save_provider_key(provider_id, value)
            self._refresh_worker_environment()
            return _success(self.settings.routing_settings())
        except ValueError as error:
            return _failure(
                BridgeError(code="invalid_provider", message=str(error))
            )
        except Exception:
            return self._internal_error("save_provider_key")

    def delete_provider_key(self, provider_id: str) -> dict[str, Any]:
        try:
            self.settings.delete_provider_key(provider_id)
            self._refresh_worker_environment()
            return _success(self.settings.routing_settings())
        except ValueError as error:
            return _failure(
                BridgeError(code="invalid_provider", message=str(error))
            )
        except Exception:
            return self._internal_error("delete_provider_key")

    def get_routing_settings(self) -> dict[str, Any]:
        return self._guard(self.settings.routing_settings)

    def save_routing_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            values = RoutingUpdate.model_validate(payload)
            saved = self.settings.save_routing_settings(values)
            self._refresh_worker_environment()
            return _success(saved)
        except (ValidationError, ValueError) as error:
            return _failure(
                BridgeError(code="invalid_routing", message=str(error))
            )
        except Exception:
            return self._internal_error("save_routing_settings")

    def probe_local_agents(self) -> dict[str, Any]:
        return self._guard(self.settings.probe_local_agents)

    def get_knowledge_snapshot(self) -> dict[str, Any]:
        return self._knowledge_guard(self.knowledge.snapshot)

    def get_knowledge_entry(
        self, name: str, rev: int | None = None
    ) -> dict[str, Any]:
        return self._knowledge_guard(lambda: self.knowledge.entry(name, rev))

    def run_knowledge_maintenance(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            request = KnowledgeCommandRequest.model_validate(payload)
        except ValidationError as error:
            return _failure(
                BridgeError(code="invalid_request", message=str(error))
            )
        return self._knowledge_guard(
            lambda: self.knowledge.maintenance(
                request.command,
                request.args,
                content=request.content,
            )
        )

    def run_knowledge_share(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = KnowledgeShareCommandRequest.model_validate(payload)
        except ValidationError as error:
            return _failure(
                BridgeError(code="invalid_request", message=str(error))
            )
        return self._knowledge_guard(
            lambda: self.knowledge.share(request.command, request.args)
        )

    def get_task_knowledge_feedback(self, task_id: str) -> dict[str, Any]:
        def read_feedback() -> dict[str, Any]:
            request = self.jobs.request_for(task_id)
            if not request.output:
                raise ValueError("该任务没有可定位的最终字幕路径。")
            return self.knowledge.feedback(request.output)

        return self._knowledge_guard(read_feedback)

    def run_refined_knowledge_update(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            values = RefinedKnowledgeUpdateRequest.model_validate(payload)
        except ValidationError as error:
            return _failure(
                BridgeError(code="invalid_request", message=str(error))
            )

        def update() -> dict[str, Any]:
            request = self.jobs.request_for(values.task_id)
            if not request.output:
                raise ValueError("该任务没有可定位的最终字幕路径。")
            return self.knowledge.refined_update(
                final_srt=request.output,
                refined_srt=values.refined_srt,
                task_id=values.task_id,
                task_summary=values.task_summary or request.task_summary,
                llm_model=values.llm_model,
                apply=values.apply,
                resume=values.resume,
            )

        return self._knowledge_guard(update)

    def open_knowledge_directory(self) -> dict[str, Any]:
        def open_directory() -> dict[str, str]:
            self.knowledge.root.mkdir(parents=True, exist_ok=True)
            self.output_opener(self.knowledge.root)
            return {"path": str(self.knowledge.root)}

        return self._guard(open_directory)

    def check_updates(self) -> dict[str, Any]:
        if self.updates is None:
            return _failure(
                BridgeError(
                    code="updates_unavailable",
                    message="当前构建未配置更新检查。",
                )
            )
        return self._guard(self.updates.check)

    def install_update(self, kind: str, version: str) -> dict[str, Any]:
        if self.updates is None or self.update_installs is None:
            return _failure(
                BridgeError(
                    code="updates_unavailable",
                    message="当前构建未配置更新安装。",
                )
            )
        if kind not in {"app", "full"}:
            return _failure(
                BridgeError(
                    code="invalid_request",
                    message=f"未知的更新类型：{kind}",
                )
            )

        def start() -> Any:
            # The kind comes from what check_updates told the UI. install()
            # re-derives it from the signed manifest and rejects a mismatch, so
            # a stale page cannot talk the backend into the wrong payload.
            return self.update_installs.start(kind, version)

        return self._guard(start)

    def get_update_install(self) -> dict[str, Any]:
        if self.update_installs is None:
            return _success(None)
        return self._guard(self.update_installs.get)

    def open_update_page(self) -> dict[str, Any]:
        if self.updates is None:
            return _failure(
                BridgeError(
                    code="updates_unavailable",
                    message="当前构建未配置更新检查。",
                )
            )

        def open_page() -> dict[str, str]:
            url = self.updates.release_url()
            self.url_opener(url)
            return {"url": url}

        return self._guard(open_page)

    def open_tasks_directory(self, task_id: str = "") -> dict[str, Any]:
        """Reveal user-data/tasks, or one task's folder inside it.

        No path comes from the caller -- only a task id the manager resolves --
        so this cannot be talked into opening somewhere else.
        """

        def open_directory() -> dict[str, str]:
            target = self.jobs.open_task_directory(task_id, self.output_opener)
            return {"path": str(target)}

        return self._guard(open_directory)

    def open_batch_directory(self, batch_id: str) -> dict[str, Any]:
        if self.batches is None:
            return _failure(
                BridgeError(code="batch_unavailable", message="当前构建不支持批处理。")
            )

        def open_directory() -> dict[str, str]:
            target = self.batches.open_batch_directory(batch_id, self.output_opener)
            return {"path": str(target)}

        return self._guard(open_directory)

    def open_batch_output(self, batch_id: str, output_path: str) -> dict[str, Any]:
        if self.batches is None:
            return _failure(
                BridgeError(code="batch_unavailable", message="当前构建不支持批处理。")
            )
        try:
            path = self.batches.open_owned_output(
                batch_id, output_path, self.output_opener
            )
            return _success({"path": str(path)})
        except ValueError:
            return _failure(
                BridgeError(
                    code="invalid_output",
                    message="无法打开不属于当前批次的路径。",
                )
            )
        except Exception:
            return self._internal_error("open_batch_output")

    def open_batch_log(self, batch_id: str) -> dict[str, Any]:
        if self.batches is None:
            return _failure(
                BridgeError(code="batch_unavailable", message="当前构建不支持批处理。")
            )

        def open_log() -> dict[str, str]:
            target = self.batches.open_log(batch_id, self.output_opener)
            return {"path": str(target)}

        return self._guard(open_log)

    def open_install_logs(self) -> dict[str, Any]:
        """Reveal the folder holding the install transcripts.

        Takes no argument, like the other reveal methods: the directory comes
        from the install manager, so this cannot be pointed elsewhere.
        """

        if self.resource_installs is None or self.resource_installs.log_dir is None:
            return _failure(
                BridgeError(
                    code="install_logs_unavailable",
                    message="当前构建没有安装日志目录。",
                )
            )

        def open_directory() -> dict[str, str]:
            target = Path(self.resource_installs.log_dir)
            target.mkdir(parents=True, exist_ok=True)
            self.output_opener(target)
            return {"path": str(target)}

        return self._guard(open_directory)

    def open_output(self, output_path: str) -> dict[str, Any]:
        def open_path() -> dict[str, str]:
            path = self.jobs.open_owned_output(output_path, self.output_opener)
            return {"path": str(path)}

        try:
            return _success(open_path())
        except ValueError:
            return _failure(
                BridgeError(
                    code="invalid_output",
                    message="无法打开不属于当前任务的路径。",
                )
            )
        except Exception:
            return self._internal_error("open_output")

    def minimize_window(self) -> dict[str, Any]:
        return self._window_action("minimize")

    def minimize_to_tray(self) -> dict[str, Any]:
        if self.tray is None:
            return _failure(
                BridgeError(
                    code="tray_unavailable",
                    message="系统托盘尚未初始化。",
                )
            )
        return self._guard(self.tray.hide_window)

    def maximize_window(self) -> dict[str, Any]:
        return self._guard(self._toggle_maximize)

    def close_window(self) -> dict[str, Any]:
        return self._window_action("destroy")

    def restart_application(self) -> dict[str, Any]:
        if self.relauncher is None:
            return _failure(
                BridgeError(
                    code="restart_unavailable",
                    message="当前构建无法自动重启，请手动重新打开 Yanami Sub。",
                )
            )
        return self._guard(self.relauncher)

    def set_window_chrome(
        self,
        background: str,
        foreground: str,
    ) -> dict[str, Any]:
        from desktop.backend.launcher.main import apply_native_window_chrome

        return self._guard(
            lambda: apply_native_window_chrome(
                self.window,
                background,
                foreground,
            )
        )

    def _window_action(self, method: str) -> dict[str, Any]:
        if self.window is None:
            return _failure(
                BridgeError(code="window_unavailable", message="窗口尚未初始化。")
            )
        return self._guard(lambda: getattr(self.window, method)())

    def _toggle_maximize(self) -> None:
        if self.window is None:
            raise ValueError("窗口尚未初始化。")
        # pywebview's own restore() is `WindowState = Normal` marshalled onto
        # the UI thread -- exactly what a maximized frameless window needs, so
        # there is no reason for this to reach into WinForms itself.
        (self.window.restore if self._is_maximized() else self.window.maximize)()

    def _is_maximized(self) -> bool:
        state = getattr(getattr(self.window, "native", None), "WindowState", "")
        name = state.ToString() if hasattr(state, "ToString") else str(state)
        return name.rsplit(".", 1)[-1].lower() == "maximized"

    def _storage_maintenance_blocker(self) -> BridgeError | None:
        task = self.jobs.snapshot()
        task_state = (
            task.get("state", "")
            if isinstance(task, dict)
            else getattr(task, "state", "")
        )
        if task_state == "running":
            return BridgeError(
                code="task_already_running",
                message="字幕任务正在运行，完成或取消后再维护数据目录。",
                action="show_current_task",
            )
        if self.batches is not None and self.batches.is_running():
            return BridgeError(
                code="batch_already_running",
                message="批处理正在运行，完成或取消后再维护数据目录。",
                action="show_batch",
            )
        if self.resource_installs is not None:
            for install in self.resource_installs.list():
                state = (
                    install.get("state", "")
                    if isinstance(install, dict)
                    else getattr(install, "state", "")
                )
                if state in {"queued", "running"}:
                    return BridgeError(
                        code="resource_install_running",
                        message="仍有资源正在下载或安装，请先暂停并等待它停下。",
                        action="open_resources",
                    )
        return None

    def _forget_resource_install_snapshots(self) -> None:
        forget = getattr(self.resource_installs, "forget_finished", None)
        if callable(forget):
            forget()

    def _after_storage_change(self) -> None:
        self._forget_resource_install_snapshots()
        storage = self._storage_state()
        set_batch_root = getattr(self.batches, "set_output_root", None)
        if callable(set_batch_root) and storage.get("tasks"):
            set_batch_root(Path(str(storage["tasks"])) / "batches")
        self._refresh_worker_environment()

    def _refresh_worker_environment(self) -> None:
        environment = self.settings.build_worker_env()
        context_builder = getattr(self.resources, "worker_context", None)
        current = self.jobs.worker_context
        if callable(context_builder):
            context = context_builder(environment)
            launch_context = WorkerLaunchContext(
                python_executable=str(context.python_executable),
                working_directory=str(context.working_directory),
                environment=dict(context.environment),
            )
        else:
            launch_context = WorkerLaunchContext(
                python_executable=current.python_executable,
                working_directory=current.working_directory,
                environment=environment,
            )
        self.jobs.set_worker_context(launch_context)
        set_batch_context = getattr(self.batches, "set_worker_context", None)
        if callable(set_batch_context):
            set_batch_context(launch_context)

    def _guard(self, action: Callable[[], Any]) -> dict[str, Any]:
        try:
            return _success(action())
        except (ValueError, KeyError) as error:
            return _failure(
                BridgeError(code="invalid_request", message=str(error))
            )
        except Exception:
            return self._internal_error(action.__name__)

    def _knowledge_guard(self, action: Callable[[], Any]) -> dict[str, Any]:
        try:
            missing = self.resources.ensure(["uv"])
            if missing:
                status = getattr(self.resources, "status", None)
                runtime = status("uv") if callable(status) else None
                message = (
                    "已检测到系统 Python；请先在“资源”中补齐 FineSub AI 依赖，"
                    "再使用知识库。"
                    if getattr(runtime, "reuses_system_python", False)
                    else "知识库运行环境尚未就绪，请先在“资源”中完成配置。"
                )
                return _failure(
                    BridgeError(
                        code="runtime_required",
                        message=message,
                        action="open_resources",
                    )
                )
            return _success(action())
        except KnowledgeOperationError as error:
            LOGGER.error("Knowledge worker failed: %s\n%s", error, error.detail)
            return _failure(
                BridgeError(code="knowledge_operation_failed", message=str(error))
            )
        except (ValueError, KeyError) as error:
            return _failure(
                BridgeError(code="invalid_request", message=str(error))
            )
        except Exception:
            return self._internal_error(action.__name__)

    @staticmethod
    def _open_in_explorer(path: Path) -> None:
        target = path if path.is_dir() else path.parent
        if os.name != "nt":
            raise OSError("Explorer integration is only available on Windows")
        os.startfile(str(target))

    @staticmethod
    def _internal_error(operation: str) -> dict[str, Any]:
        LOGGER.exception("Desktop bridge operation failed: %s", operation)
        return _failure(
            BridgeError(
                code="internal_error",
                message="操作失败，请查看应用日志后重试。",
            )
        )
