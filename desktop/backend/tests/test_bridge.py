from __future__ import annotations

from pathlib import Path

import pytest

from finesub import config as app_config
from finesub.llm.routing.model_routes import default_model_routes
from finesub_bootstrap.http_client import NetworkConnectionError
from finesub_bootstrap.models import ResourceStatus
from desktop.backend.common.models import BatchRequest, TaskRequest
from desktop.backend.jobs.launch import WorkerLaunchContext
from desktop.backend.launcher.bridge import DesktopBridge
from finesub_bootstrap.environment import WorkerContext
from desktop.backend.settings.store import SettingsStore


@pytest.fixture(autouse=True)
def clear_routing_caches():
    app_config.clear_config_cache()
    default_model_routes.cache_clear()
    yield
    app_config.clear_config_cache()
    default_model_routes.cache_clear()


class FakeJobs:
    def __init__(self) -> None:
        self.requests = []
        self.worker_context = WorkerLaunchContext(
            python_executable="python.exe",
            working_directory=None,
            environment={},
        )

    def set_worker_context(self, context: WorkerLaunchContext) -> None:
        self.worker_context = context

    def start(self, request):
        self.requests.append(request)
        return {
            "taskId": "task-1",
            "state": "running",
            "request": request.model_dump(mode="json"),
            "events": [],
        }

    def snapshot(self):
        return None

    def history(self):
        return []

    def open_task_directory(self, task_id, opener):
        target = Path(task_id or ".").resolve()
        opener(target)
        return target

    def open_owned_output(self, output_path, opener):
        path = Path(output_path).expanduser().resolve()
        owned = {
            Path(value).expanduser().resolve()
            for snapshot in self.history()
            for value in snapshot.get("outputs", {}).values()
        }
        if path not in owned:
            raise ValueError("Output path is not owned by a saved task")
        opener(path)
        return path

    def events_after(self, after_cursor=0):
        return [], max(0, int(after_cursor))

    def cancel(self, task_id: str):
        return {"taskId": task_id, "state": "cancelled", "events": []}


class FakeResources:
    def __init__(self) -> None:
        self.ready = True
        self.ensured: list[tuple[str, ...]] = []
        self.interpreter_refreshes: list[bool] = []
        self.configured_interpreters: list[Path | None] = []

    def check_all(self):
        return [
            ResourceStatus(
                id="ffmpeg",
                version="7.1",
                state="ready",
            )
        ]

    def task_ready(self, request=None):
        return self.ready

    def diagnostics(self):
        return {
            "healthy": self.ready,
            "core_version": "0.5.1",
            "resources": self.check_all(),
            "blocking_resources": [],
            "python_executable": Path("C:/FineSub/runtime/python/python.exe"),
            "disk_free_bytes": 1024,
            "paths": {"tasks": Path("C:/FineSub/tasks")},
        }

    def ensure(self, resource_ids):
        # The bridge now asks which of *these* are missing, so the fake has to
        # answer per resource rather than with one global flag.
        self.ensured.append(tuple(resource_ids))
        return [] if self.ready else list(resource_ids)

    def install(self, resource_id, progress):
        self.ready = True
        return ResourceStatus(id=resource_id, version="1", state="ready")

    def worker_context(self, extra_env):
        return WorkerContext(
            python_executable=Path("C:/FineSub/runtime/python/python.exe"),
            working_directory=Path("C:/FineSub/app/current"),
            environment={**extra_env, "FINESUB_MODEL_DIR": "C:/FineSub/models"},
        )

    def interpreter_choice(self, *, refresh=False):
        self.interpreter_refreshes.append(refresh)
        return {
            "configured": None,
            "found": "C:/Python312/python.exe",
            "version": "3.12.6",
            "detail": "",
            "rejected": [],
        }

    def configure_interpreter(self, path):
        self.configured_interpreters.append(path)
        return path


class FakeUpdates:
    def check(self):
        return {
            "available": True,
            "version": "1.1.0",
            "releaseUrl": "https://github.com/tuzibuqiahuluobo/yanami-sub/releases/tag/v1.1.0",
        }

    def release_url(self):
        return "https://github.com/tuzibuqiahuluobo/yanami-sub/releases/tag/v1.1.0"


class FakeTray:
    def __init__(self) -> None:
        self.hidden = False

    def hide_window(self) -> None:
        self.hidden = True


class FakeBatches:
    def __init__(self) -> None:
        self.running = False
        self.requests: list[BatchRequest] = []
        self.worker_context: WorkerLaunchContext | None = None
        self.output_root: Path | None = None
        self.imported_path: Path | None = None
        self.exported: tuple[Path, BatchRequest] | None = None

    def is_running(self) -> bool:
        return self.running

    def start(self, request: BatchRequest):
        self.requests.append(request)
        self.running = True
        return {"batch_id": "batch-1", "state": "running", "items": []}

    def snapshot(self):
        return None

    def history(self):
        return []

    def request_for(self, batch_id: str) -> BatchRequest:
        if not self.requests:
            raise KeyError(batch_id)
        return self.requests[-1]

    def import_manifest(self, path: Path):
        self.imported_path = Path(path).resolve()
        return BatchRequest.model_validate({"items": [{"input": "D:/media/a.wav"}]}), ["output"]

    def export_manifest(self, path: Path, request: BatchRequest):
        destination = Path(path).resolve()
        self.exported = (destination, request)
        return {"path": str(destination), "count": len(request.items)}

    def cancel(self, batch_id: str):
        self.running = False
        return {"batch_id": batch_id, "state": "cancelled", "items": []}

    def resume(self, batch_id: str):
        self.running = True
        return {"batch_id": batch_id, "state": "running", "items": []}

    def set_worker_context(self, context: WorkerLaunchContext) -> None:
        self.worker_context = context

    def set_output_root(self, output_root: Path) -> None:
        self.output_root = Path(output_root).resolve()


class FakeKnowledge:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[tuple[str, object]] = []

    def snapshot(self):
        self.calls.append(("snapshot", None))
        return {"revision": 7, "entries": []}

    def entry(self, name: str, rev: int | None = None):
        self.calls.append(("entry", (name, rev)))
        return {"qualified_name": name, "valid_from_rev": rev or 7, "text": "# entry"}

    def maintenance(self, command: str, args: list[str], *, content: str = ""):
        self.calls.append(("maintenance", (command, args, content)))
        return {"command": command, "exit_code": 0, "output": "ok"}

    def share(self, command: str, args: list[str]):
        self.calls.append(("share", (command, args)))
        return {"command": command, "exit_code": 0, "output": "ok"}

    def feedback(self, final_srt: str):
        self.calls.append(("feedback", final_srt))
        return {"artifact_dir": "artifacts", "merged_hints": []}

    def refined_update(self, **values):
        self.calls.append(("refined_update", values))
        return {"mode": "refined_aligned", "warnings": []}


def _bridge(tmp_path: Path) -> tuple[DesktopBridge, FakeJobs]:
    jobs = FakeJobs()
    bridge = DesktopBridge(
        jobs=jobs,
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
    )
    return bridge, jobs


def test_bridge_exposes_a_structured_diagnostic_report(tmp_path: Path) -> None:
    bridge, _ = _bridge(tmp_path)

    result = bridge.get_diagnostics()

    assert result["ok"] is True
    assert result["data"]["healthy"] is True
    assert result["data"]["core_version"] == "0.5.1"
    assert result["data"]["python_executable"].endswith("python.exe")
    assert result["data"]["gpu"] == {"state": "unavailable", "devices": []}


def test_bridge_refreshes_python_discovery_for_an_explicit_check(
    tmp_path: Path,
) -> None:
    resources = FakeResources()
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=resources,
        settings=SettingsStore(tmp_path / "user-data"),
    )

    result = bridge.get_python_interpreter()

    assert result["ok"] is True
    assert result["data"]["found"].endswith("python.exe")
    assert resources.interpreter_refreshes == [True]


def test_bridge_rejects_unknown_task_fields(tmp_path: Path) -> None:
    bridge, _ = _bridge(tmp_path)

    result = bridge.start_task({"input": "a.wav", "command": "calc.exe"})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_request"


def test_bridge_blocks_translation_without_key_but_allows_raw(
    tmp_path: Path,
) -> None:
    bridge, jobs = _bridge(tmp_path)

    translated = bridge.start_task({"input": "a.wav", "stage": "final-srt"})
    raw = bridge.start_task({"input": "a.wav", "stage": "raw-srt"})

    assert translated["ok"] is False
    assert translated["error"]["code"] == "api_key_required"
    assert translated["error"]["action"] == "open_settings"
    assert raw["ok"] is True
    assert jobs.requests[-1].stage == "raw-srt"


def test_bridge_requests_runtime_install_before_worker_launch(
    tmp_path: Path,
) -> None:
    jobs = FakeJobs()
    resources = FakeResources()
    resources.ready = False
    bridge = DesktopBridge(
        jobs=jobs,
        resources=resources,
        settings=SettingsStore(tmp_path / "user-data"),
    )

    result = bridge.start_task({"input": "a.wav", "stage": "raw-srt"})

    assert result["ok"] is False
    assert result["error"]["code"] == "runtime_required"
    assert result["error"]["action"] == "open_resources"
    assert jobs.requests == []


def test_bridge_starts_a_core_batch_and_requests_url_capabilities(
    tmp_path: Path,
) -> None:
    jobs = FakeJobs()
    batches = FakeBatches()
    resources = FakeResources()
    bridge = DesktopBridge(
        jobs=jobs,
        batches=batches,
        resources=resources,
        settings=SettingsStore(tmp_path / "user-data"),
    )

    result = bridge.start_batch(
        {
            "items": [
                {"input": "D:/media/a.wav"},
                {"input": "https://example.test/video"},
            ]
        }
    )

    assert result["ok"] is True
    assert batches.requests[0].workers.download == 2
    assert resources.ensured[-1] == ("uv", "ffmpeg", "yt-dlp")


def test_bridge_imports_and_exports_manifests_only_through_native_dialogs(
    tmp_path: Path,
) -> None:
    batches = FakeBatches()
    imported_path = tmp_path / "import.jsonl"
    exported_path = tmp_path / "export.jsonl"
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        batches=batches,
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        batch_manifest_selector=lambda: str(imported_path),
        batch_manifest_export_selector=lambda: str(exported_path),
    )

    imported = bridge.import_batch_manifest()
    exported = bridge.export_batch_manifest(imported["data"]["request"])

    assert imported["ok"] is True
    assert imported["data"]["ignored_fields"] == ["output"]
    assert batches.imported_path == imported_path.resolve()
    assert exported["ok"] is True
    assert exported["data"]["count"] == 1
    assert batches.exported is not None
    assert batches.exported[0] == exported_path.resolve()


def test_single_task_is_blocked_while_a_batch_is_running(tmp_path: Path) -> None:
    batches = FakeBatches()
    batches.running = True
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        batches=batches,
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
    )

    result = bridge.start_task({"input": "D:/media/a.wav"})

    assert result["ok"] is False
    assert result["error"]["code"] == "batch_already_running"
    assert result["error"]["action"] == "show_batch"


def test_save_api_keys_returns_only_configuration_status(tmp_path: Path) -> None:
    bridge, jobs = _bridge(tmp_path)

    result = bridge.save_api_keys(
        {"gemini": "private-gemini-key", "exa": "", "tavily": ""}
    )

    assert result["ok"] is True
    assert result["data"]["api_keys"]["gemini_free"] == "configured"
    assert result["data"]["api_keys"]["gemini_paid"] == "missing"
    assert "private-gemini-key" not in str(result)
    assert jobs.worker_context.environment["GEMINI_FREE"] == "private-gemini-key"


def test_reveal_api_keys_returns_plaintext_entries(tmp_path: Path) -> None:
    bridge, _ = _bridge(tmp_path)
    bridge.save_api_keys({"gemini": "private-gemini-key-123"})

    result = bridge.reveal_api_keys()

    assert result["ok"] is True
    entries = result["data"]["gemini_free"]
    assert entries[0]["key"] == "private-gemini-key-123"
    assert entries[0]["masked"] == "priv…-123"
    assert result["data"]["exa"] == []


def test_preferences_round_trip_through_the_bridge(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    bridge, _ = _bridge(tmp_path)

    saved = bridge.save_preferences(
        {"ui": {"language": "en"}, "task_defaults": {"gpu_tier": "standard"}}
    )
    assert saved["ok"] is True

    loaded = bridge.get_preferences()

    assert loaded["ok"] is True
    assert loaded["data"]["preferences"]["ui"] == {"language": "en"}
    assert loaded["data"]["preferences"]["task_defaults"]["gpu_tier"] == "standard"
    # The shared half travels with it: one call is what the panel needs to draw.
    assert loaded["data"]["shared"]["split_length_scale"] is None
    assert loaded["data"]["config_path"].endswith("config.toml")


def test_unset_task_defaults_never_reach_the_wire(tmp_path: Path, monkeypatch) -> None:
    # The front end spreads task_defaults straight over the task request, so a
    # null here is not "unset" -- it overwrites a real default and every task
    # start then fails validation. Assert on the serialized payload, not on the
    # model: that is where the nulls used to appear.
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    bridge, _ = _bridge(tmp_path)
    bridge.save_preferences({"task_defaults": {"gpu_tier": "standard"}})

    defaults = bridge.get_bootstrap_state()["data"]["preferences"]["task_defaults"]

    assert defaults == {"gpu_tier": "standard"}
    assert TaskRequest.model_validate({"input": "a.mp4", **defaults}).gpu_tier == "standard"


def test_saving_one_preference_section_leaves_the_other_alone(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    bridge, _ = _bridge(tmp_path)
    bridge.save_preferences({"ui": {"language": "en"}})

    bridge.save_preferences({"task_defaults": {"gpu_tier": "standard"}})
    # null clears one setting without touching the rest of its section.
    bridge.save_preferences({"ui": {"closeWindowAction": "close"}})
    bridge.save_preferences({"ui": {"closeWindowAction": None}})

    preferences = bridge.get_preferences()["data"]["preferences"]
    assert preferences["ui"] == {"language": "en"}
    assert preferences["task_defaults"]["gpu_tier"] == "standard"


def test_saving_a_shared_setting_refreshes_the_worker_environment(
    tmp_path: Path, monkeypatch
) -> None:
    # The worker learns config.toml's location from its launch environment,
    # which only names the file if it already existed when the launcher started.
    # Creating it from the panel therefore has to rebuild that environment, or
    # the next task runs at the default and the panel looks broken.
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    bridge, jobs = _bridge(tmp_path)
    before = jobs.worker_context

    result = bridge.save_shared_settings({"split_length_scale": 0.8})

    assert result["ok"] is True
    assert jobs.worker_context is not before


def test_an_invalid_shared_setting_is_refused_with_a_reason(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    bridge, _ = _bridge(tmp_path)

    result = bridge.save_shared_settings({"split_length_scale": 4.0})

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_settings"
    assert "length scale" in result["error"]["message"]
    assert not (tmp_path / "config.toml").exists()


def test_bootstrap_state_reports_resources_and_optional_capabilities(
    tmp_path: Path,
) -> None:
    bridge, _ = _bridge(tmp_path)

    result = bridge.get_bootstrap_state()

    assert result["ok"] is True
    assert result["data"]["app_version"] == "development"
    assert result["data"]["resources"][0]["state"] == "ready"
    assert result["data"]["capabilities"]["raw_srt"] is True
    assert result["data"]["capabilities"]["translation"] is False
    assert result["data"]["routing"]["active_preset_id"] == "default"


def test_bridge_saves_a_validated_core_routing_preset(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(tmp_path / "config.toml"))
    app_config.clear_config_cache()
    default_model_routes.cache_clear()
    bridge, jobs = _bridge(tmp_path)
    current = bridge.get_routing_settings()["data"]
    before = jobs.worker_context

    result = bridge.save_routing_settings(
        {
            "preset": "agy-hybrid",
            "execution_policy": current["execution_policy"],
            "local_agent_timeout_seconds": 900,
            "local_agent_allow_unisolated_user_config": False,
            "local_agent_service_tier": "",
            "local_agent_reasoning_effort": "",
            "local_agent_max_parallel": 2,
        }
    )

    assert result["ok"] is True
    assert result["data"]["active_preset_id"] == "agy-hybrid"
    assert result["data"]["local_agent_max_parallel"] == 2
    assert jobs.worker_context is not before


def test_resource_install_refreshes_worker_context(tmp_path: Path) -> None:
    bridge, jobs = _bridge(tmp_path)

    result = bridge.install_resource("uv")

    assert result["ok"] is True
    assert jobs.worker_context.python_executable.endswith("python.exe")
    assert jobs.worker_context.working_directory == "C:\\FineSub\\app\\current"
    assert jobs.worker_context.environment["FINESUB_MODEL_DIR"] == "C:/FineSub/models"


def test_resource_status_refresh_uses_authoritative_catalog(tmp_path: Path) -> None:
    bridge, _ = _bridge(tmp_path)

    result = bridge.get_resource_statuses()

    assert result["ok"] is True
    assert result["data"][0]["id"] == "ffmpeg"
    assert result["data"][0]["state"] == "ready"


def test_update_check_opens_release_page_without_installing(
    tmp_path: Path,
) -> None:
    opened: list[str] = []
    jobs = FakeJobs()
    bridge = DesktopBridge(
        jobs=jobs,
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        updates=FakeUpdates(),
        url_opener=opened.append,
    )

    checked = bridge.check_updates()
    opened_result = bridge.open_update_page()

    assert checked["data"]["available"] is True
    assert opened_result["ok"] is True
    assert opened == [
        "https://github.com/tuzibuqiahuluobo/yanami-sub/releases/tag/v1.1.0"
    ]


def test_update_network_failure_suggests_switching_network_and_is_logged(
    tmp_path: Path,
) -> None:
    class OfflineUpdates:
        def check(self):
            raise NetworkConnectionError("所有连接方式均失败")

    recorded: list[tuple[str, BaseException]] = []
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        updates=OfflineUpdates(),
        error_reporter=lambda context, error: recorded.append((context, error)),
    )

    result = bridge.check_updates()

    assert result["error"]["code"] == "network_error"
    assert "切换网络" in result["error"]["message"]
    assert "关闭代理" in result["error"]["message"]
    assert recorded[0][0] == "bridge.check"
    assert isinstance(recorded[0][1], NetworkConnectionError)


def test_open_output_accepts_any_saved_task_but_rejects_other_paths(
    tmp_path: Path,
) -> None:
    older_output = tmp_path / "older" / "subtitle.srt"
    current_output = tmp_path / "current" / "subtitle.srt"
    opened: list[Path] = []

    class JobsWithHistory(FakeJobs):
        def snapshot(self):
            return {"outputs": {"rawSrt": str(current_output)}}

        def history(self):
            return [
                {"outputs": {"rawSrt": str(current_output)}},
                {"outputs": {"finalSrt": str(older_output)}},
            ]

    bridge = DesktopBridge(
        jobs=JobsWithHistory(),
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        output_opener=opened.append,
    )

    accepted = bridge.open_output(str(older_output))
    rejected = bridge.open_output(str(tmp_path / "not-a-task-output.txt"))

    assert accepted["ok"] is True
    assert opened == [older_output.resolve()]
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "invalid_output"


def test_minimize_to_tray_hides_window_through_tray_controller(
    tmp_path: Path,
) -> None:
    tray = FakeTray()
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        tray=tray,
    )

    result = bridge.minimize_to_tray()

    assert result["ok"] is True
    assert tray.hidden is True


def test_maximize_button_toggles_between_maximized_and_normal(
    tmp_path: Path,
) -> None:
    class NativeWindow:
        WindowState = "Normal"

    class FakeWindow:
        native = NativeWindow()

        def maximize(self) -> None:
            self.native.WindowState = "Maximized"

        def restore(self) -> None:
            self.native.WindowState = "Normal"

    window = FakeWindow()
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        window=window,
    )

    assert bridge.maximize_window()["ok"] is True
    assert window.native.WindowState == "Maximized"
    assert bridge.maximize_window()["ok"] is True
    assert window.native.WindowState == "Normal"


def test_restart_application_uses_the_configured_relauncher(tmp_path: Path) -> None:
    calls: list[str] = []
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        relauncher=lambda: calls.append("restart"),
    )

    result = bridge.restart_application()

    assert result["ok"] is True
    assert calls == ["restart"]


def test_api_key_help_opens_only_audited_official_pages(tmp_path: Path) -> None:
    opened: list[str] = []
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        url_opener=opened.append,
    )

    accepted = bridge.open_external_url(
        "https://aistudio.google.com/app/apikey"
    )
    rejected = bridge.open_external_url("https://example.test/key")

    assert accepted["ok"] is True
    assert opened == ["https://aistudio.google.com/app/apikey"]
    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "invalid_request"


def test_the_missing_resource_is_named_rather_than_guessed(tmp_path: Path) -> None:
    # "请先安装 Python 运行环境和 FFmpeg" was the whole message regardless of what
    # was actually missing. With git and yt-dlp installed on demand, a user told
    # to install FFmpeg when yt-dlp is what is missing has no way to act on it.
    class OnlyYtDlpMissing:
        def check_all(self):
            return []

        def ensure(self, resource_ids):
            return [item for item in resource_ids if item == "yt-dlp"]

    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=OnlyYtDlpMissing(),
        settings=SettingsStore(tmp_path / "user-data"),
    )

    result = bridge.start_task(
        {"input": "https://example.test/v", "stage": "raw-srt"}
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "runtime_required"
    assert "yt-dlp" in result["error"]["message"]
    assert "FFmpeg" not in result["error"]["message"]


def test_bridge_forwards_owned_knowledge_workflows_and_rejects_unknown_commands(
    tmp_path: Path,
) -> None:
    final_srt = tmp_path / "task" / "subtitle.srt"

    class JobsWithRequest(FakeJobs):
        def request_for(self, task_id: str) -> TaskRequest:
            assert task_id == "task-1"
            return TaskRequest(input="D:/media/a.wav", output=str(final_srt))

    knowledge = FakeKnowledge(tmp_path / "knowledge")
    bridge = DesktopBridge(
        jobs=JobsWithRequest(),
        resources=FakeResources(),
        settings=SettingsStore(tmp_path / "user-data"),
        knowledge=knowledge,
    )

    assert bridge.get_knowledge_snapshot()["data"]["revision"] == 7
    assert bridge.get_knowledge_entry("common/FineSub", 4)["ok"] is True
    assert bridge.run_knowledge_maintenance(
        {"command": "edit", "args": ["common/FineSub"], "content": "# changed"}
    )["ok"] is True
    assert bridge.run_knowledge_share(
        {"command": "status", "args": ["--remote", "https://example.test"]}
    )["ok"] is True
    assert bridge.get_task_knowledge_feedback("task-1")["ok"] is True
    assert bridge.run_refined_knowledge_update(
        {
            "task_id": "task-1",
            "refined_srt": str(tmp_path / "refined.srt"),
            "apply": False,
        }
    )["ok"] is True
    rejected = bridge.run_knowledge_maintenance(
        {"command": "shell", "args": ["calc.exe"]}
    )

    assert rejected["ok"] is False
    assert rejected["error"]["code"] == "invalid_request"
    assert ("feedback", str(final_srt)) in knowledge.calls
    refined = next(value for kind, value in knowledge.calls if kind == "refined_update")
    assert refined["final_srt"] == str(final_srt)
    assert refined["task_id"] == "task-1"


def test_bridge_routes_missing_knowledge_runtime_to_resources(tmp_path: Path) -> None:
    resources = FakeResources()
    resources.ready = False
    knowledge = FakeKnowledge(tmp_path / "knowledge")
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=resources,
        settings=SettingsStore(tmp_path / "user-data"),
        knowledge=knowledge,
    )

    result = bridge.get_knowledge_snapshot()

    assert result["ok"] is False
    assert result["error"]["code"] == "runtime_required"
    assert result["error"]["action"] == "open_resources"
    assert "请先安装 Python 运行环境" not in result["error"]["message"]
    assert knowledge.calls == []


def test_bridge_does_not_tell_system_python_users_to_install_python(
    tmp_path: Path,
) -> None:
    class SystemPythonResources(FakeResources):
        def status(self, resource_id: str) -> ResourceStatus:
            assert resource_id == "uv"
            return ResourceStatus(
                id="uv",
                version="3.12",
                state="missing",
                reuses_system_python=True,
            )

    resources = SystemPythonResources()
    resources.ready = False
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=resources,
        settings=SettingsStore(tmp_path / "user-data"),
        knowledge=FakeKnowledge(tmp_path / "knowledge"),
    )

    result = bridge.get_knowledge_snapshot()

    assert result["ok"] is False
    assert "请先安装 Python 运行环境" not in result["error"]["message"]
    assert "已检测到系统 Python" in result["error"]["message"]
    assert "AI 依赖" in result["error"]["message"]
    assert result["error"]["action"] == "open_resources"


def test_bridge_picks_up_a_key_written_from_outside_the_application(
    tmp_path: Path,
) -> None:
    """The data root is shared with the CLI on purpose, so a key can appear
    while the application is running. Every backend read already goes to the
    file; what went stale was the worker environment the launcher built at
    start-up, which is what `reload_settings` re-arms."""

    user_data = tmp_path / "user-data"
    settings = SettingsStore(user_data)
    jobs = FakeJobs()
    bridge = DesktopBridge(
        jobs=jobs,
        resources=FakeResources(),
        settings=settings,
    )
    assert bridge.reload_settings()["data"]["settings"]["api_keys"][
        "gemini_free"
    ] == "missing"

    # As if the CLI, or the user, wrote it.
    user_data.mkdir(parents=True, exist_ok=True)
    (user_data / ".env").write_text("GEMINI_FREE=from-elsewhere\n", encoding="utf-8")

    result = bridge.reload_settings()

    assert result["ok"] is True
    assert result["data"]["settings"]["api_keys"]["gemini_free"] == "configured"
    assert result["data"]["capabilities"]["translation"] is True


def test_bridge_exports_keys_only_through_the_native_save_selector(
    tmp_path: Path,
) -> None:
    settings = SettingsStore(tmp_path / "user-data")
    settings.save_api_keys(gemini="secret")
    destination = tmp_path / "transfer.env"
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=FakeResources(),
        settings=settings,
        key_export_selector=lambda: str(destination),
    )

    result = bridge.export_api_keys()

    assert result["ok"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["path"] == str(destination.resolve())
    assert destination.read_text(encoding="utf-8") == "GEMINI_FREE=secret\n"


def test_bridge_relocates_storage_and_refreshes_future_batch_paths(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "large-files"

    class MaintenanceResources(FakeResources):
        def __init__(self) -> None:
            super().__init__()
            self.root = tmp_path / "app"
            self.calls: list[tuple[str, object]] = []

        def storage_state(self):
            return {
                "big_data": str(self.root),
                "default_big_data": str(tmp_path / "app"),
                "runtime": str(tmp_path / "app" / "runtime"),
                "models": str(self.root / "models"),
                "cache": str(self.root / "cache"),
                "tasks": str(self.root / "tasks"),
                "agent_capsules": str(self.root / "agent"),
                "relocated": self.root != tmp_path / "app",
            }

        def relocate_big_data(self, selected, *, reset=False):
            self.calls.append(("relocate", (selected, reset)))
            self.root = Path(selected).resolve()
            return {
                "storage": self.storage_state(),
                "resources": self.check_all(),
                "message": "moved",
            }

    class FinishedInstalls:
        forgotten = False

        def list(self):
            return []

        def forget_finished(self):
            self.forgotten = True

    resources = MaintenanceResources()
    installs = FinishedInstalls()
    batches = FakeBatches()
    bridge = DesktopBridge(
        jobs=FakeJobs(),
        batches=batches,
        resources=resources,
        resource_installs=installs,
        settings=SettingsStore(tmp_path / "user-data"),
        directory_selector=lambda: str(destination),
    )

    result = bridge.relocate_data()

    assert result["ok"] is True
    assert result["data"]["storage"]["big_data"] == str(destination.resolve())
    assert resources.calls == [("relocate", (destination, False))]
    assert installs.forgotten is True
    assert batches.output_root == (destination / "tasks" / "batches").resolve()
    assert batches.worker_context is not None


def test_storage_maintenance_is_blocked_while_a_resource_install_runs(
    tmp_path: Path,
) -> None:
    class RunningInstalls:
        def list(self):
            return [{"state": "running"}]

    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=FakeResources(),
        resource_installs=RunningInstalls(),
        settings=SettingsStore(tmp_path / "user-data"),
        directory_selector=lambda: str(tmp_path / "large-files"),
    )

    result = bridge.relocate_data()

    assert result["ok"] is False
    assert result["error"]["code"] == "resource_install_running"


def test_rebuildable_cleanup_requires_an_explicit_confirmation(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class MaintenanceResources(FakeResources):
        def purge_rebuildable_data(self):
            calls.append("purge")
            return {"storage": {}, "resources": [], "message": "removed"}

    bridge = DesktopBridge(
        jobs=FakeJobs(),
        resources=MaintenanceResources(),
        settings=SettingsStore(tmp_path / "user-data"),
    )

    rejected = bridge.purge_rebuildable_data("yes")
    accepted = bridge.purge_rebuildable_data("PURGE_REBUILDABLE_DATA")

    assert rejected["error"]["code"] == "confirmation_required"
    assert accepted["ok"] is True
    assert calls == ["purge"]
