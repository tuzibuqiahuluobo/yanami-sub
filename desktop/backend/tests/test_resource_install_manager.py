from __future__ import annotations

from pathlib import Path
import time

from finesub_bootstrap.models import DownloadProgress, ResourceStatus
from finesub_bootstrap.downloader import DownloadPaused
from desktop.backend.resources.install_manager import ResourceInstallManager


class FakeResources:
    def __init__(self, root: Path) -> None:
        self.root = root

    def status(self, resource_id: str) -> ResourceStatus:
        return ResourceStatus(id=resource_id, version="1.0", state="missing")

    def locations(self, resource_id: str) -> tuple[Path, Path]:
        return (
            self.root / "cache" / f"{resource_id}.zip",
            self.root / "runtime" / resource_id,
        )

    def install(self, resource_id, progress, *, stage, log, should_pause):
        stage("downloading", "正在下载资源文件")
        for step in range(1, 21):
            if should_pause():
                raise DownloadPaused()
            progress(
                DownloadProgress(
                    downloaded=step * 5,
                    total=100,
                    bytes_per_second=50,
                )
            )
            time.sleep(0.01)
        return ResourceStatus(id=resource_id, version="1.0", state="ready")


def _wait_for(manager: ResourceInstallManager, resource_id: str, state: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        snapshot = manager.get(resource_id)
        if snapshot is not None and snapshot.state == state:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"resource did not reach state {state}")


def _wait_for_progress(manager: ResourceInstallManager, resource_id: str):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        snapshot = manager.get(resource_id)
        if snapshot is not None and snapshot.total > 0:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("resource did not report download progress")


def test_resource_install_runs_in_background_and_reports_progress(
    tmp_path: Path,
) -> None:
    manager = ResourceInstallManager(FakeResources(tmp_path))

    started = manager.start("ffmpeg")

    assert started.state in {"queued", "running"}
    running = _wait_for_progress(manager, "ffmpeg")
    assert running.total == 100
    assert running.downloaded > 0
    completed = _wait_for(manager, "ffmpeg", "ready")
    assert completed.phase == "complete"


def test_dependency_stage_clears_bootstrap_archive_progress(tmp_path: Path) -> None:
    class Dependencies(FakeResources):
        def install(self, resource_id, progress, *, stage, log, should_pause):
            progress(DownloadProgress(downloaded=100, total=100, bytes_per_second=50))
            stage("installing_dependencies", "正在安装 FineSub AI 依赖")
            return ResourceStatus(id=resource_id, version="1.0", state="ready")

    manager = ResourceInstallManager(Dependencies(tmp_path))
    manager.start("uv")
    finished = _wait_for(manager, "uv", "ready")
    assert finished.downloaded == 0
    assert finished.total == 0
    assert finished.bytes_per_second == 0


def test_failed_python_install_exposes_the_verified_manual_download(tmp_path: Path) -> None:
    class FailedResources(FakeResources):
        def install(self, resource_id, progress, *, stage, log, should_pause):
            raise RuntimeError("Failed to install: wheel.whl")

        def manual_download(self, resource_id, error):
            assert resource_id == "uv"
            return {"filename": "wheel.whl", "url": "https://example.org/wheel.whl"}

    manager = ResourceInstallManager(FailedResources(tmp_path))
    manager.start("uv")

    failed = _wait_for(manager, "uv", "failed")
    assert failed.manual_download == {
        "filename": "wheel.whl",
        "url": "https://example.org/wheel.whl",
    }


def test_failure_state_survives_broken_manual_help(tmp_path: Path) -> None:
    class FailedResources(FakeResources):
        def install(self, resource_id, progress, *, stage, log, should_pause):
            raise RuntimeError("download failed")

        def manual_download(self, resource_id, error):
            raise ValueError("invalid lock")

    manager = ResourceInstallManager(FailedResources(tmp_path))
    manager.start("uv")

    failed = _wait_for(manager, "uv", "failed")
    assert failed.error == "download failed"
    assert failed.manual_download is None
    assert any("invalid lock" in line for line in failed.logs)


def test_different_resources_download_concurrently(tmp_path: Path) -> None:
    manager = ResourceInstallManager(FakeResources(tmp_path))

    manager.start("ffmpeg")
    manager.start("git")

    assert _wait_for_progress(manager, "ffmpeg").state == "running"
    assert _wait_for_progress(manager, "git").state == "running"
    assert _wait_for(manager, "ffmpeg", "ready").state == "ready"
    assert _wait_for(manager, "git", "ready").state == "ready"


def test_resource_install_pause_preserves_paths_and_can_resume(
    tmp_path: Path,
) -> None:
    manager = ResourceInstallManager(FakeResources(tmp_path))
    manager.start("uv")
    _wait_for_progress(manager, "uv")

    manager.pause("uv")

    paused = _wait_for(manager, "uv", "paused")
    assert paused.downloaded < paused.total
    assert paused.cache_path.endswith("uv.zip")
    resumed = manager.start("uv")
    assert resumed.state in {"queued", "running"}
    assert _wait_for(manager, "uv", "ready").state == "ready"


def test_shutdown_pauses_and_joins_an_active_install(tmp_path: Path) -> None:
    manager = ResourceInstallManager(FakeResources(tmp_path))
    manager.start("models")
    manager.start("git")
    _wait_for_progress(manager, "models")
    _wait_for_progress(manager, "git")

    manager.shutdown()

    assert _wait_for(manager, "models", "paused").state == "paused"
    assert _wait_for(manager, "git", "paused").state == "paused"
    assert not manager._workers["models"].is_alive()
    assert not manager._workers["git"].is_alive()


def test_finished_install_snapshots_can_be_forgotten_after_a_move(
    tmp_path: Path,
) -> None:
    manager = ResourceInstallManager(FakeResources(tmp_path))
    manager.start("ffmpeg")
    _wait_for(manager, "ffmpeg", "ready")

    manager.forget_finished()

    assert manager.list() == []


def test_active_install_snapshots_cannot_be_forgotten(tmp_path: Path) -> None:
    manager = ResourceInstallManager(FakeResources(tmp_path))
    manager.start("ffmpeg")
    _wait_for_progress(manager, "ffmpeg")

    try:
        import pytest

        with pytest.raises(RuntimeError, match="正在安装"):
            manager.forget_finished()
    finally:
        manager.shutdown()
