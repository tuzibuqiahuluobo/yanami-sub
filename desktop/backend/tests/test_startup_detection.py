from __future__ import annotations

import subprocess
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from desktop.backend.launcher import main as launcher
from desktop.backend.launcher.session_log import SessionLog
from desktop.backend.launcher.startup import StartupCancelled, StartupWindow
from desktop.backend.settings import local_agents, store as store_module
from desktop.backend.settings.store import SettingsStore
from finesub.llm.agent import local_agent


def test_upstream_codex_probes_are_hidden_without_changing_other_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(local_agent, "subprocess", subprocess)
    monkeypatch.setattr(local_agent, "_resolve_shell_free_command", lambda _command: ["codex.exe"])
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: (
        calls.append((args, kwargs)) or SimpleNamespace(returncode=0, stdout="codex-cli 1.159.2", stderr="")
    ))
    monkeypatch.setattr(local_agents, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    with local_agents.bounded_agent_probe(time.monotonic() + 60):
        local_agent.CodexLocalAgentDriver().probe()
    assert len(calls) == 4
    assert all(kwargs["creationflags"] & 0x08000000 for _, kwargs in calls)
    assert all(kwargs["stdin"] == subprocess.DEVNULL for _, kwargs in calls)
    assert all(0 < kwargs["timeout"] <= 15 for _, kwargs in calls)
    local_agent.subprocess.run(["explicit-interactive-command"])
    assert calls[-1][1] == {}
    assert subprocess is not local_agent.subprocess


@pytest.mark.skipif(os.name != "nt", reason="Windows console visibility")
def test_probe_child_has_no_windows_console(monkeypatch):
    monkeypatch.setattr(local_agent, "subprocess", subprocess)
    with local_agents.bounded_agent_probe(time.monotonic() + 15):
        result = local_agent.subprocess.run(
            [sys.executable, "-I", "-c", "import ctypes; print(bool(ctypes.windll.kernel32.GetConsoleWindow()))"],
            capture_output=True, text=True, check=True,
        )
    assert result.stdout.strip() == "False"


@pytest.mark.parametrize("cancelled", [False, True])
def test_expired_or_cancelled_probe_never_creates_a_child(monkeypatch, cancelled):
    monkeypatch.setattr(local_agent, "subprocess", subprocess)
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: pytest.fail("Unexpected child"))
    cancel = threading.Event()
    if cancelled:
        cancel.set()
    with local_agents.bounded_agent_probe(time.monotonic() + (60 if cancelled else -1), cancel):
        with pytest.raises(subprocess.TimeoutExpired):
            local_agent.subprocess.run(["slow-agent", "--help"])


def test_probe_honours_the_remaining_whole_scan_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(local_agent, "subprocess", subprocess)
    monkeypatch.setattr(local_agents, "time", SimpleNamespace(monotonic=lambda: 100))
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(kwargs))
    with local_agents.bounded_agent_probe(102):
        local_agent.subprocess.run(["slow-agent"], timeout=60)
    assert calls[0]["timeout"] == 2


def test_concurrent_scans_share_one_result_but_later_manual_scans_refresh(tmp_path, monkeypatch):
    store = SettingsStore(tmp_path)
    entered, second_requested, release = (threading.Event() for _ in range(3))
    calls, results = [], []
    lock = threading.Lock()

    class CoordinatedLock:
        def __enter__(self):
            if threading.current_thread().name == "second-probe":
                second_requested.set()
            lock.acquire()

        def __exit__(self, *_args):
            lock.release()

    def probe(**_kwargs):
        calls.append(True)
        entered.set()
        assert release.wait(2)
        return []

    monkeypatch.setattr(store, "_agent_probe_lock", CoordinatedLock())
    monkeypatch.setattr(store, "_probe_local_agents", probe)
    first = threading.Thread(target=lambda: results.append(store.probe_local_agents()))
    second = threading.Thread(target=lambda: results.append(store.probe_local_agents()), name="second-probe")
    try:
        first.start()
        assert entered.wait(2)
        second.start()
        assert second_requested.wait(2)
    finally:
        release.set()
        first.join(2)
        if second.ident is not None:
            second.join(2)
    assert results == [[], []] and len(calls) == 1
    store.probe_local_agents()
    assert len(calls) == 2


def test_overall_budget_stops_launching_remaining_agents(tmp_path, monkeypatch):
    from finesub.llm.routing import execution_policy, model_routes

    now = [0.0]
    calls, progress = [], []
    tiers = ["LOCAL_AGY", "LOCAL_CODEX", "LOCAL_DSH"]
    routes = SimpleNamespace(
        targets={tier: SimpleNamespace(backend="local_agent") for tier in tiers},
        target_fact=lambda tier: SimpleNamespace(provider_tier=tier, api_model_id="test", effective_quota_pool=""),
    )

    class Driver:
        driver_id = "test"

        def probe(self):
            calls.append(True)
            now[0] = 61
            return SimpleNamespace(available=False, version="", failure_kind="broken", error="timed out")

    monkeypatch.setattr(store_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(store_module, "configure_local_agents", lambda _path: {})
    monkeypatch.setattr(model_routes, "default_model_routes", lambda: routes)
    monkeypatch.setattr(execution_policy, "load_execution_settings", lambda: None)
    monkeypatch.setattr(execution_policy, "driver_for_provider_tier", lambda *_args, **_kwargs: Driver())
    statuses = SettingsStore(tmp_path).probe_local_agents(progress=progress.append)
    assert len(calls) == 1
    assert [status.status for status in statuses] == ["broken", "error", "error"]
    assert "60 秒" in statuses[1].detail
    assert any("耗时 61.0 秒" in message for message in progress)


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        for handler in self.handlers:
            handler()


@pytest.fixture
def application(tmp_path, monkeypatch):
    import webview

    order, options = [], {}
    resources = SimpleNamespace(install_manager=SimpleNamespace(shutdown=lambda: order.append("stop-resources")))
    jobs = SimpleNamespace(shutdown=lambda: order.append("stop-jobs"))
    batches = SimpleNamespace(shutdown=lambda: order.append("stop-batches"))
    settings = SimpleNamespace(probe_local_agents=lambda **_kwargs: (order.append("probe") or []))
    window = SimpleNamespace(
        events=SimpleNamespace(loaded=Event(), closed=Event()),
        show=lambda: order.append("show-main"), destroy=lambda: order.append("destroy-main"),
    )

    def create_window(*_args, **kwargs):
        order.append("create-main")
        options.update(kwargs)
        return window

    monkeypatch.setenv("FINESUB_APP_ROOT", str(tmp_path))
    monkeypatch.setenv("YANAMI_SUB_DEV_URL", "http://127.0.0.1:3000")
    monkeypatch.setattr(webview, "create_window", create_window)
    monkeypatch.setattr(launcher, "create_backend_services", lambda *_args, **_kwargs: (jobs, batches, resources, settings))
    monkeypatch.setattr(launcher, "DesktopBridge", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(launcher, "TrayController", lambda *_args: SimpleNamespace(start=lambda: None, stop=lambda: None))
    monkeypatch.setattr(launcher, "expose_bridge", lambda *_args: None)
    startup = StartupWindow()
    monkeypatch.setattr(startup, "close", lambda: order.append("close-startup"))
    return SimpleNamespace(order=order, options=options, window=window, startup=startup, settings=settings)


def test_main_is_hidden_until_prechecks_and_page_load_complete(application):
    app = application
    window, bridge, _ = launcher.create_application(startup=app.startup)
    assert app.order == ["probe", "create-main"]
    assert bridge.startup_agent_statuses == []
    assert app.options["hidden"] is True
    window.events.loaded.fire()
    assert app.order[-2:] == ["close-startup", "show-main"]


def test_optional_detection_failure_does_not_prevent_opening(application):
    def failing_probe(**_kwargs):
        raise RuntimeError("broken optional CLI")

    application.settings.probe_local_agents = failing_probe
    _, bridge, _ = launcher.create_application(SessionLog.disabled(), startup=application.startup)
    assert bridge.startup_agent_statuses == []
    application.window.events.loaded.fire()
    assert application.order[-1] == "show-main"


def test_cancelled_startup_stops_services_and_never_opens_the_main_window(application):
    application.startup.cancelled.set()
    with pytest.raises(StartupCancelled):
        launcher.create_application(startup=application.startup)
    assert application.order == ["stop-resources", "stop-jobs", "stop-batches"]


def test_cancellation_during_page_load_does_not_reopen_a_closed_startup(application):
    launcher.create_application(startup=application.startup)
    application.startup.cancelled.set()
    application.window.events.loaded.fire()
    assert "show-main" not in application.order
    assert application.order[-1] == "destroy-main"


def test_startup_window_without_gui_still_logs_and_tracks_cancellation(monkeypatch):
    from desktop.backend.launcher import startup as module

    log = []
    monkeypatch.setattr(module, "os", SimpleNamespace(name="posix"))
    window = StartupWindow(log.append)
    window.start()
    window.update("正在检测 DSH，请稍后…")
    assert log == ["startup check: 正在检测 DSH，请稍后…"]
    window.cancelled.set()
    with pytest.raises(StartupCancelled):
        window.check_cancelled()
    window.close()
    assert window._close.is_set()


@pytest.mark.skipif(os.name != "nt", reason="Native WinForms startup")
def test_native_startup_window_renders_and_closes_without_a_webview(tmp_path):
    log = []
    window = StartupWindow(log.append)
    try:
        window.start()
        assert window._ready.is_set(), log
        assert window._form is not None, log
        assert window._thread.IsAlive, log
        from System import Action
        from System.Drawing import Bitmap, Rectangle
        from System.Drawing.Imaging import ImageFormat
        window.update("正在检测 CODEX（2/5），请稍后…")
        form = window._form

        def render():
            # Render this component itself, not the user's desktop or other apps.
            bitmap = Bitmap(form.Width, form.Height)
            try:
                form.DrawToBitmap(bitmap, Rectangle(0, 0, form.Width, form.Height))
                bitmap.Save(str(tmp_path / "startup-window.png"), ImageFormat.Png)
                assert form.ClientSize.Width == 460
                assert form.Controls.Count == 3
            finally:
                bitmap.Dispose()

        form.Invoke(Action(render))
        assert (tmp_path / "startup-window.png").stat().st_size > 100
    finally:
        window.close()
        if window._thread is not None:
            assert window._thread.Join(3000), log
    assert not window.cancelled.is_set()


def test_task_precheck_hides_its_console_and_disables_interactive_input(monkeypatch):
    from desktop.backend.worker import agent_health_check

    calls = []
    monkeypatch.setattr(agent_health_check, "_executable_exists", lambda _path: True)
    monkeypatch.setattr(agent_health_check.subprocess, "run", lambda args, **kwargs: (
        calls.append(kwargs) or SimpleNamespace(returncode=0)
    ))
    assert agent_health_check._check_agent_tier("LOCAL_CODEX", ["codex.exe"]).available
    assert calls[0]["creationflags"] == (subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    assert calls[0]["stdin"] == subprocess.DEVNULL
