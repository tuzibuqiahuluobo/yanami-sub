from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import sys

import finesub_bootstrap
from finesub_bootstrap.paths import AppPaths
from desktop.YanamiSub import _activate_packaged_source
from desktop.backend.common.product import INSTALLED_MARKER_NAME
from desktop.backend.launcher.main import (
    DESKTOP_UV_ASSET,
    DESKTOP_UV_VERSION,
    _load_resources,
    create_backend_services,
    dropped_file_path,
    expose_bridge,
    load_update_service,
    relaunch_application,
    resolve_app_version,
    resolve_application_paths,
    resolve_application_source,
    resolve_frontend_url,
)
from desktop.backend.updates.installer import AppInstaller
from desktop.backend.launcher.bridge import DesktopBridge
from desktop.backend.settings.store import SettingsStore


RUNTIME_MANIFEST = (
    Path(finesub_bootstrap.__file__).resolve().parent / "runtime-manifest.json"
)


def test_desktop_uv_bootstrap_is_pinned_without_rewriting_upstream_manifest(
    tmp_path: Path,
) -> None:
    source = tmp_path / "app"
    package = source / "src" / "finesub_bootstrap"
    package.mkdir(parents=True)
    shutil.copy2(RUNTIME_MANIFEST, package / "runtime-manifest.json")
    manager = _load_resources(AppPaths.for_root(tmp_path), source)
    assert manager.resources["uv"].version == DESKTOP_UV_VERSION
    assert manager.resources["uv"].asset.sha256 == DESKTOP_UV_ASSET["sha256"]
    upstream = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    assert upstream["resources"][0]["version"] != DESKTOP_UV_VERSION
    newer = json.loads((package / "runtime-manifest.json").read_text(encoding="utf-8"))
    newer["resources"][0]["version"] = "0.13.0"
    (package / "runtime-manifest.json").write_text(
        json.dumps(newer), encoding="utf-8"
    )
    updated = _load_resources(AppPaths.for_root(tmp_path), source)
    assert updated.resources["uv"].version == "0.13.0"


def test_frozen_entrypoint_activates_the_versioned_core_before_startup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "app" / "versions" / "1.2.0" / "src"
    (source / "finesub").mkdir(parents=True)
    (source / "finesub" / "pipeline.py").write_text("ok", encoding="utf-8")
    (source.parent / "pyproject.toml").write_text("[project]", encoding="utf-8")
    (tmp_path / "app" / "current.json").write_text(
        '{"current":"1.2.0"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("FINESUB_APP_ROOT", str(tmp_path))
    original_path = list(sys.path)
    try:
        _activate_packaged_source()
        assert sys.path[0] == str(source.resolve())
    finally:
        sys.path[:] = original_path
    entrypoint = (Path(__file__).resolve().parents[2] / "YanamiSub.py").read_text(
        encoding="utf-8"
    )
    assert entrypoint.index("\nif _STARTUP_ALLOWED:\n") < entrypoint.index(
        "    _activate_packaged_source()"
    ) < entrypoint.index("    from desktop.backend.launcher.main import main")


def test_personal_data_is_the_same_place_for_every_form(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Installed and portable copies used to disagree, which is how one user
    # ended up with three knowledge bases. The install directory still owns the
    # big, rebuildable half.
    installed = tmp_path / "Programs" / "Yanami Sub"
    installed.mkdir(parents=True)
    (installed / INSTALLED_MARKER_NAME).write_text("", encoding="utf-8")
    portable = tmp_path / "FineSubPortable"
    portable.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    expected = (tmp_path / "LocalAppData").resolve() / "FineSub" / "user-data"

    assert resolve_application_paths(installed).user_data == expected
    assert resolve_application_paths(portable).user_data == expected
    assert resolve_application_paths(installed).runtime == (
        installed.resolve() / "runtime"
    )
    assert resolve_application_paths(portable).models == (
        portable.resolve() / "models"
    )


def test_development_url_takes_precedence(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")

    assert (
        resolve_frontend_url(paths, development_url="http://127.0.0.1:3000")
        == "http://127.0.0.1:3000"
    )


def test_relaunch_starts_the_new_instance_before_closing_this_one(
    tmp_path: Path,
    monkeypatch,
) -> None:
    events: list[object] = []
    executable = tmp_path / "Yanami Sub.exe"

    class FakeWindow:
        def destroy(self) -> None:
            events.append("destroy")

    def launch(command, **options):
        events.append((command, options))

    monkeypatch.setattr("desktop.backend.launcher.main.subprocess.Popen", launch)

    relaunch_application(FakeWindow(), executable=executable)

    assert events == [
        (
            [str(executable.resolve())],
            {"cwd": str(tmp_path.resolve()), "close_fds": True},
        ),
        "destroy",
    ]


def test_app_version_follows_installed_current_pointer(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    paths.app_current.parent.mkdir(parents=True)
    paths.app_current.write_text(
        '{"current":"2.3.4","previous":null,"pendingHealth":false}',
        encoding="utf-8",
    )

    assert resolve_app_version(paths) == "2.3.4"


def test_native_drop_uses_pywebview_full_path_only() -> None:
    assert (
        dropped_file_path(
            {
                "dataTransfer": {
                    "files": [
                        {
                            "name": "video.mp4",
                            "pywebviewFullPath": "C:/media/video.mp4",
                        }
                    ]
                }
            }
        )
        == "C:/media/video.mp4"
    )
    assert (
        dropped_file_path(
            {"dataTransfer": {"files": [{"name": "video.mp4"}]}}
        )
        is None
    )


def test_bridge_exposes_only_the_public_desktop_api(tmp_path: Path) -> None:
    exposed: list[str] = []

    class FakeWindow:
        def expose(self, *functions: object) -> None:
            exposed.extend(function.__name__ for function in functions)

    bridge = DesktopBridge(
        jobs=object(),
        resources=object(),
        settings=SettingsStore(tmp_path),
    )

    expose_bridge(FakeWindow(), bridge)

    assert exposed == [
        "get_bootstrap_state",
        "get_diagnostics",
        "select_input_file",
        "select_batch_files",
        "import_batch_manifest",
        "export_batch_manifest",
        "export_task_log",
        "open_task_log_export_location",
        "start_task",
        "cancel_task",
        "retry_task",
        "resume_task",
        "delete_task_intermediates",
        "get_task_snapshot",
        "list_tasks",
        "poll_events",
        "start_batch",
        "cancel_batch",
        "resume_batch",
        "get_batch_snapshot",
        "list_batches",
        "install_resource",
        "get_resource_install",
        "list_resource_installs",
        "get_resource_statuses",
        "get_download_route",
        "set_download_route",
        "pause_resource_install",
        "open_resource_location",
        "open_resource_dependency_download",
        "get_python_interpreter",
        "select_python_interpreter",
        "set_python_interpreter",
        "clear_python_interpreter",
        "rescan_gpus",
        "get_preferences",
        "save_preferences",
        "save_shared_settings",
        "reload_settings",
        "save_api_keys",
        "delete_api_key",
        "reveal_api_keys",
        "export_api_keys",
        "get_routing_settings",
        "save_routing_settings",
        "save_provider_key",
        "delete_provider_key",
        "probe_local_agents",
        "get_knowledge_snapshot",
        "get_knowledge_entry",
        "run_knowledge_maintenance",
        "run_knowledge_share",
        "get_task_knowledge_feedback",
        "run_refined_knowledge_update",
        "open_knowledge_directory",
        "check_updates",
        "install_update",
        "get_update_install",
        "open_update_page",
        "open_external_url",
        "open_tasks_directory",
        "open_batch_directory",
        "open_batch_output",
        "open_batch_log",
        "open_install_logs",
        "open_output",
        "relocate_data",
        "purge_rebuildable_data",
        "minimize_window",
        "minimize_to_tray",
        "maximize_window",
        "close_window",
        "restart_application",
        "set_window_chrome",
    ]


def test_installed_static_frontend_uses_app_current_pointer(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    frontend = (
        paths.app_versions / "1.2.0" / "desktop" / "frontend" / "out" / "index.html"
    )
    frontend.parent.mkdir(parents=True)
    frontend.write_text("<html></html>", encoding="utf-8")
    paths.app_current.parent.mkdir(parents=True, exist_ok=True)
    paths.app_current.write_text(
        '{"current":"1.2.0","previous":"1.1.0","pendingHealth":false}',
        encoding="utf-8",
    )

    resolved = resolve_frontend_url(paths)

    assert resolved == str(frontend.resolve())


def test_pending_broken_app_rolls_back_to_previous_frontend(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    previous = (
        paths.app_versions / "1.1.0" / "desktop" / "frontend" / "out" / "index.html"
    )
    previous.parent.mkdir(parents=True)
    previous.write_text("<html>previous</html>", encoding="utf-8")
    installer = AppInstaller(paths)
    installer.write_pointer(
        current="1.2.0",
        previous="1.1.0",
        pending_health=True,
    )

    resolved = resolve_frontend_url(paths, installer=installer)

    pointer = json.loads(paths.app_current.read_text(encoding="utf-8"))
    assert resolved == str(previous.resolve())
    assert pointer["current"] == "1.1.0"


def test_development_static_frontend_falls_back_to_repo_copy(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    frontend = paths.root / "desktop" / "frontend" / "out" / "index.html"
    frontend.parent.mkdir(parents=True)
    frontend.write_text("<html></html>", encoding="utf-8")

    assert resolve_frontend_url(paths) == str(frontend.resolve())


def test_installed_worker_source_follows_current_app_pointer(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path)
    source = paths.app_versions / "1.2.0"
    (source / "src" / "finesub").mkdir(parents=True)
    (source / "src" / "finesub" / "pipeline.py").write_text("ok", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]", encoding="utf-8")
    paths.app_current.parent.mkdir(parents=True, exist_ok=True)
    paths.app_current.write_text(
        '{"current":"1.2.0","previous":"1.1.0","pendingHealth":false}',
        encoding="utf-8",
    )

    assert resolve_application_source(paths) == source.resolve()


def test_development_services_run_worker_from_repository_source(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    (paths.root / "src" / "finesub").mkdir(parents=True)
    (paths.root / "src" / "finesub" / "pipeline.py").write_text("ok", encoding="utf-8")
    (paths.root / "pyproject.toml").write_text("[project]", encoding="utf-8")
    resources = paths.root / "src" / "finesub_bootstrap"
    resources.mkdir(parents=True)
    shutil.copy2(
        RUNTIME_MANIFEST,
        resources / "runtime-manifest.json",
    )
    python = tmp_path / "venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"python")

    jobs, batches, desktop_resources, _ = create_backend_services(
        paths,
        development_python=python,
    )

    assert jobs.worker_context.python_executable == str(python.resolve())
    assert jobs.worker_context.working_directory == str(paths.root)
    assert batches.snapshot() is None
    # A development interpreter is not considered ready merely because the
    # executable exists; it must also contain the worker dependencies.
    assert desktop_resources.check_all()[0].state == "missing"


def test_installed_services_load_resources_from_current_app_version(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    source = paths.app_versions / "1.2.0"
    (source / "src" / "finesub").mkdir(parents=True)
    (source / "src" / "finesub" / "pipeline.py").write_text("ok", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]", encoding="utf-8")
    resources = source / "src" / "finesub_bootstrap"
    resources.mkdir(parents=True)
    shutil.copy2(
        RUNTIME_MANIFEST,
        resources / "runtime-manifest.json",
    )
    paths.app_current.parent.mkdir(parents=True, exist_ok=True)
    paths.app_current.write_text(
        '{"current":"1.2.0","previous":null,"pendingHealth":false}',
        encoding="utf-8",
    )

    jobs, batches, desktop_resources, _ = create_backend_services(paths)

    assert jobs.worker_context.working_directory == str(source.resolve())
    assert batches.snapshot() is None
    statuses = desktop_resources.check_all()
    # Required first, then request-specific and optional conveniences. URL
    # tasks gate on yt-dlp at launch; local tasks do not wait for it or Git.
    assert [status.id for status in statuses] == [
        "uv",
        "ffmpeg",
        "git",
        "yt-dlp",
        "tokcount",
        "models",
    ]
    assert [status.optional for status in statuses] == [
        False,
        False,
        True,
        True,
        True,
        True,
    ]


def test_update_service_loads_only_with_configured_trusted_key(
    tmp_path: Path,
) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    paths.root.mkdir(parents=True)
    (paths.root / "launcher.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "appVersion": "1.0.0",
                "launcherVersion": "1.0.0",
                "channel": "stable",
                "platform": "windows-x64",
                "releaseRepository": "tuzibuqiahuluobo/yanami-sub",
            }
        ),
        encoding="utf-8",
    )
    (paths.root / "trusted-update-keys.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "keys": {
                    "release-key": base64.b64encode(b"k" * 32).decode("ascii")
                },
            }
        ),
        encoding="utf-8",
    )

    service = load_update_service(paths)

    assert service is not None
    assert service.config.release_repository == "tuzibuqiahuluobo/yanami-sub"
    assert service.trusted_keys == {
        "release-key": base64.b64encode(b"k" * 32).decode("ascii")
    }


def test_update_service_is_disabled_for_placeholder_key(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path / "FineSub")
    paths.root.mkdir(parents=True)
    shutil.copy2(
        Path(__file__).parents[2] / "resources" / "launcher.example.json",
        paths.root / "launcher.json",
    )
    shutil.copy2(
        Path(__file__).parents[2]
        / "resources"
        / "trusted-update-keys.example.json",
        paths.root / "trusted-update-keys.json",
    )

    assert load_update_service(paths) is None
