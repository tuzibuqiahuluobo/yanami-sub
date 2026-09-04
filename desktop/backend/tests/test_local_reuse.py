from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

from finesub_bootstrap.models import DownloadAsset, ResourceSpec
from finesub_bootstrap.paths import AppPaths
from finesub_bootstrap.resources import ResourceManager

from desktop.backend.resources.local_reuse import LocalResourceReuse


def _resource_manager(root: Path, body: bytes) -> ResourceManager:
    return ResourceManager(
        AppPaths.for_root(root),
        [
            ResourceSpec(
                id="demo",
                version="1.2.3",
                destination="runtime",
                directory="demo",
                archive_type="zip",
                required_files=["bin/demo.exe"],
                asset=DownloadAsset(
                    url="https://downloads.example/demo-1.2.3.zip",
                    size=len(body),
                    sha256=hashlib.sha256(body).hexdigest(),
                ),
            )
        ],
    )


def _archive(path: Path, payload: bytes = b"executable") -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("bin/demo.exe", payload)
    return path.read_bytes()


def test_matching_local_archive_is_verified_cached_and_installed_offline(
    tmp_path: Path,
) -> None:
    local = tmp_path / "somewhere" / "demo-1.2.3.zip"
    body = _archive(local)
    manager = _resource_manager(tmp_path / "managed", body)
    messages: list[str] = []
    reuse = LocalResourceReuse(manager, search_roots=[tmp_path / "somewhere"])

    result = reuse.prepare("demo", log=messages.append)
    status = manager.install("demo", lambda _progress: None)

    assert result.path == manager.cache_path("demo")
    assert result.path.read_bytes() == body
    assert status.state == "ready"
    assert manager.active_file("demo", "demo.exe") is not None
    assert any("已复用本机资源" in line for line in messages)


def test_same_named_archive_with_wrong_version_is_rejected(tmp_path: Path) -> None:
    expected = tmp_path / "expected.zip"
    body = _archive(expected, b"right version")
    candidate = tmp_path / "downloads" / "demo-1.2.3.zip"
    _archive(candidate, b"old version")
    manager = _resource_manager(tmp_path / "managed", body)
    messages: list[str] = []

    result = LocalResourceReuse(
        manager,
        search_roots=[candidate.parent],
    ).prepare("demo", log=messages.append)

    assert result.path is None
    assert result.rejected == 1
    assert not manager.cache_path("demo").exists()
    assert any("目标版本不符" in line for line in messages)


def test_the_disk_index_is_reused_across_resource_preparations(
    tmp_path: Path,
) -> None:
    body = _archive(tmp_path / "downloads" / "demo-1.2.3.zip")
    manager = _resource_manager(tmp_path / "managed", body)
    reuse = LocalResourceReuse(manager, search_roots=[tmp_path / "downloads"])

    first = reuse.prepare("demo")
    (tmp_path / "downloads" / "later" / "demo-1.2.3.zip").parent.mkdir()
    (tmp_path / "downloads" / "later" / "demo-1.2.3.zip").write_bytes(body)
    second = reuse.prepare("demo")

    assert first.path == manager.cache_path("demo")
    assert second.path == manager.cache_path("demo")
    assert len(reuse._candidates["demo-1.2.3.zip"]) == 1
