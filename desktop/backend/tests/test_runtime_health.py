from pathlib import Path
from types import SimpleNamespace

import pytest

from finesub.config import clear_config_cache
from finesub_bootstrap.models import ResourceStatus
from desktop.backend.common.core_compat import unified_llm_contract
from desktop.backend.common.models import BatchItemRequest, BatchRequest, BridgeError, TaskRequest
from desktop.backend.launcher.bridge import DesktopBridge
from desktop.backend.resources.runtime_health import RuntimeHealth


class Runtime:
    development_python = None
    def __init__(self, root):
        self.paths = SimpleNamespace(user_data=root / "user-data")
        self.app_source = root / "app"
        self.app_source.mkdir()
        (self.app_source / "VERSION").write_text("0.1.3-rc.1", encoding="utf-8")
        self.runtime_root = root / "runtime"
        self.runtime_root.mkdir()
        self.reason, self.calls, self.busy = "ready", 0, False
        from finesub_bootstrap.runtime_health import RuntimeReport
        self.report = RuntimeReport()
    def condition(self):
        return self.reason
    def check(self):
        self.calls += 1
        return self.report
    def health_detail(self):
        return "instant check failed"
    def refuse_if_in_use(self):
        if self.busy:
            raise RuntimeError("another run holds the runtime")


@pytest.fixture
def managed(tmp_path, monkeypatch):
    if not unified_llm_contract():
        pytest.skip("0.6.0 managed runtime contract")
    config = tmp_path / "任意配置名.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("FINESUB_CONFIG_FILE", str(config))
    clear_config_cache()
    runtime = Runtime(tmp_path)
    yield runtime, RuntimeHealth(runtime), config
    clear_config_cache()


def test_legacy_runtime_never_calls_new_health_apis():
    runtime = SimpleNamespace(development_python=None)
    health = RuntimeHealth(runtime)
    assert health.assess() is None and health.install_options() == {}
    ready = ResourceStatus(id="uv", version="test", state="ready")
    assert health.status(ready) is ready


@pytest.mark.parametrize("policy,checks", [("off", 0), ("on", 2), ("auto", 1)])
def test_core_policy_and_success_marker_control_checks_without_polling(managed, policy, checks):
    from finesub_bootstrap.runtime_health import record_success
    runtime, health, config = managed
    config.write_text(f'[runtime]\nintegrity_check="{policy}"\n', encoding="utf-8")
    ready = ResourceStatus(id="uv", version="test", state="ready")
    for _ in range(3):
        assert health.status(ready).usable
    assert runtime.calls == 0
    assert health.assess() is None
    record_success(runtime.runtime_root, health.version)
    assert health.assess() is None
    assert runtime.calls == checks


def test_disabled_auto_repair_in_custom_named_config_is_respected_but_manual_repair_is_allowed(managed):
    runtime, health, config = managed
    config.write_text("[runtime]\nauto_repair=false\n", encoding="utf-8")
    runtime.report.missing_files = {"torch": ["missing.bin"]}
    runtime.report.extras = [("custom-package", "1.0")]
    error = health.assess()
    assert error.code == "runtime_repair_disabled"
    assert not health.status(ResourceStatus(id="uv", version="test", state="ready")).usable
    logs, stages = [], []
    assert health.install_options(log=logs.append, stage=lambda *args: stages.append(args)) == {"force": True, "verify_hashes": True}
    assert any("custom-package" in line for line in logs) and stages
    health.installed()
    assert health.reason == ""


def test_default_user_data_config_uses_the_same_fallback_as_settings(managed, monkeypatch):
    runtime, health, _config = managed
    monkeypatch.delenv("FINESUB_CONFIG_FILE")
    monkeypatch.setattr("finesub.paths.resolve_config_file", lambda *args: None)
    runtime.paths.user_data.mkdir()
    (runtime.paths.user_data / "config.toml").write_text("[runtime]\nauto_repair=false\n", encoding="utf-8")
    runtime.reason = "outdated"
    assert health.assess().code == "runtime_repair_disabled"


def test_automatic_repair_rechecks_policy_when_the_queued_install_actually_starts(managed):
    from desktop.backend.resources.desktop_service import DesktopResourceService
    runtime, health, config = managed
    runtime.reason = "outdated"
    assert health.assess() is None
    config.write_text("[runtime]\nauto_repair=false\n", encoding="utf-8")
    service = object.__new__(DesktopResourceService)
    service.runtime, service.runtime_health = runtime, health
    with pytest.raises(RuntimeError, match="disabled"):
        service.install("uv", lambda _event: None, automatic=True)


@pytest.mark.parametrize("reason", ["outdated", "damaged"])
def test_repair_of_an_instantly_broken_runtime_still_reports_extra_packages(managed, reason):
    runtime, health, _config = managed
    runtime.reason = reason
    runtime.report.extras = [("user-added-package", "1.0")]
    logs = []
    assert health.install_options(log=logs.append)["force"]
    assert runtime.calls == 1
    assert any("user-added-package" in line for line in logs)


@pytest.mark.parametrize("reason", ["outdated", "damaged", "absent"])
def test_first_install_is_distinct_from_replacement(managed, reason):
    runtime, health, config = managed
    runtime.reason = reason
    config.write_text("[runtime]\nauto_repair=false\n", encoding="utf-8")
    error = health.assess()
    assert (error is None) == (reason == "absent")


@pytest.mark.parametrize("setting", ['integrity_check=["off"]', 'auto_repair="false"', 'integrity_check="bad"', '[broken'])
def test_invalid_policy_never_falls_back_to_automatic_replacement(managed, setting):
    _runtime, health, config = managed
    config.write_text("[runtime]\n" + setting, encoding="utf-8")
    assert health.assess().code == "runtime_check_failed"


def test_explicit_diagnostics_override_off_but_busy_repair_never_starts(managed):
    runtime, health, config = managed
    config.write_text('[runtime]\nintegrity_check="off"\n', encoding="utf-8")
    assert health.assess() is None and runtime.calls == 0
    runtime.report.missing_packages = ["torch"]
    assert health.assess(explicit=True) is None and health.reason == "mismatched"
    calls = runtime.calls
    assert health.assess() is None and runtime.calls == calls
    runtime.busy = True
    with pytest.raises(RuntimeError, match="another run"):
        health.install_options()


def test_task_batch_and_automatic_install_preserve_structured_runtime_errors():
    error = BridgeError(code="runtime_repair_disabled", message="manual repair required", action="open_resources")
    instance = object.__new__(DesktopBridge)
    instance.resources = SimpleNamespace(prepare_runtime=lambda: error, ensure=lambda _: [])
    request = TaskRequest(input="video")
    assert instance._missing_resources(request) is error
    assert instance._missing_batch_resources(BatchRequest(items=[BatchItemRequest(input="video")])) is error
    instance.resource_installs = SimpleNamespace(start=lambda _: {})
    instance._prepare_download_route = lambda: None
    assert instance.install_resource("uv", automatic=True)["error"]["code"] == "runtime_repair_disabled"
    assert instance.install_resource("uv")["ok"]  # Explicit user request bypasses automatic policy, not core leases.


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 active-runtime refusal")
def test_actual_core_refuses_other_runtime_leases(tmp_path):
    from finesub_bootstrap.environment import RuntimeEnvironment, RuntimeInUse
    from finesub_bootstrap.locks import holding_activity
    from finesub_bootstrap.paths import AppPaths
    paths = AppPaths.for_root(tmp_path)
    runtime = RuntimeEnvironment(paths=paths, app_source=tmp_path, uv_executable=lambda: tmp_path / "uv.exe")
    runtime.runtime_root.mkdir(parents=True)
    with holding_activity(paths.user_data):
        with pytest.raises(RuntimeInUse):
            runtime.refuse_if_in_use()
        runtime.refuse_if_in_use(holds_lease=True)
        with holding_activity(paths.user_data):
            with pytest.raises(RuntimeInUse):
                runtime.refuse_if_in_use(holds_lease=True)


@pytest.mark.skipif(not unified_llm_contract(), reason="0.6.0 success marker")
def test_worker_success_marker_is_core_owned_and_failure_is_only_a_warning(tmp_path, monkeypatch, capsys):
    from desktop.backend.worker.runtime import record_runtime_success
    from finesub_bootstrap.runtime_health import should_check_before_run
    root = tmp_path / "runtime"
    root.mkdir()
    monkeypatch.setenv("YANAMI_RUNTIME_ROOT", str(root))
    monkeypatch.setenv("YANAMI_RUNTIME_VERSION", "desktop-version")
    record_runtime_success()
    assert not should_check_before_run("auto", root, "desktop-version")
    def fail(*args):
        raise OSError("cannot write marker")
    monkeypatch.setattr("finesub_bootstrap.runtime_health.record_success", fail)
    record_runtime_success()
    assert "cannot write marker" in capsys.readouterr().err


def test_failure_rechecks_even_after_previous_success_without_starting_repair(managed):
    from finesub_bootstrap.runtime_health import record_success
    runtime, health, _config = managed
    record_success(runtime.runtime_root, health.version)
    assert health.assess() is None and runtime.calls == 0
    runtime.report.missing_files = {"torch": ["later-missing.bin"]}
    runtime.busy = True  # A read-only failure check must not try to acquire a repair slot.
    note = health.failure_note()
    assert runtime.calls == 1 and health.reason == "mismatched"
    assert "later-missing.bin" in note and "未自动" in note


def test_failure_check_off_does_not_run_a_full_check_or_hide_original_error(managed):
    runtime, health, config = managed
    config.write_text('[runtime]\nintegrity_check="off"\n', encoding="utf-8")
    assert "skipped by policy" in health.failure_note()
    assert runtime.calls == 0
