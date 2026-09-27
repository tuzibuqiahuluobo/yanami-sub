from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re

from pydantic import BaseModel, ConfigDict

from finesub_bootstrap.archive import safe_extract_zip
from finesub_bootstrap.fsops import remove_tree
from finesub_bootstrap.paths import AppPaths
from desktop.backend.updates.manifest import UpdateManifest


REQUIRED_APP_FILES = (
    # The three that a run needs together: the entry point, the runner it
    # hands items to and the conversion it drives. A staging that dropped any
    # one of them fails at import -- after the switch, on the user's machine.
    "src/finesub/pipeline.py",
    "src/finesub/scheduler.py",
    "src/finesub/stages.py",
    "desktop/backend/worker/main.py",
    "desktop/frontend/out/index.html",
    "pyproject.toml",
    "app-manifest.json",
)

RC7_REQUIRED_MODULES = (
    "desktop/backend/worker/agent_health_check.py",
    "desktop/backend/worker/model_source.py",
    "desktop/backend/settings/local_agents.py",
)


def validate_app_directory(
    root: Path, *, version: str | None = None, platform: str | None = None
) -> None:
    """Check immutable app files, including hashes in RC7.1+ payloads."""

    required = REQUIRED_APP_FILES + (RC7_REQUIRED_MODULES if version == "0.1.0-rc.7" else ())
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"App update is missing required files: {missing}")
    body = json.loads((root / "app-manifest.json").read_text(encoding="utf-8"))
    if not isinstance(body, dict) or (version is not None and body.get("version") != version):
        raise ValueError("App archive version does not match its directory")
    if platform is not None and body.get("platform") != platform:
        raise ValueError("App archive platform does not match update manifest")
    files = body.get("files")
    if files is None:
        if version == "0.1.0-rc.7.post1":
            raise ValueError("RC7.1 app manifest requires per-file integrity hashes")
        return  # legacy snapshots predate per-file digests
    if not isinstance(files, dict) or not files or len(files) > 20_000:
        raise ValueError("App integrity file list is invalid")
    for name, metadata in files.items():
        if (
            not isinstance(name, str) or not name or "\\" in name or ":" in name
            or PurePosixPath(name).is_absolute() or PurePosixPath(name).as_posix() != name
            or ".." in PurePosixPath(name).parts
            or name == "app-manifest.json" or not isinstance(metadata, dict)
        ):
            raise ValueError("App integrity path is invalid")
        path = root.joinpath(*PurePosixPath(name).parts)
        size, digest = metadata.get("size"), metadata.get("sha256")
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(f"App file is missing: {name}")
        if not isinstance(size, int) or isinstance(size, bool) or path.stat().st_size != size:
            raise ValueError(f"App file size differs: {name}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"App file digest is invalid: {name}")
        checksum = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                checksum.update(chunk)
        actual = checksum.hexdigest()
        if actual != digest:
            raise ValueError(f"App file digest differs: {name}")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_file()
        and path.relative_to(root).as_posix() != "app-manifest.json"
    }
    if actual_files != set(files):
        raise ValueError("App integrity file list does not match the version directory")


class PendingSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    previous: str | None
    pending_health: bool


class AppInstaller:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.pointer_path = paths.root / "app" / "current.json"

    def install(
        self,
        archive_path: Path,
        manifest: UpdateManifest,
    ) -> PendingSwitch:
        archive_path = archive_path.expanduser().resolve()
        self._verify_archive(archive_path, manifest)
        self.paths.app_versions.mkdir(parents=True, exist_ok=True)
        staging = self.paths.app_versions / f"{manifest.version}.staging"
        final = self.paths.app_versions / manifest.version
        remove_tree(staging)
        if final.exists():
            # Reinstalling a version that is already unpacked used to be a hard
            # FileExistsError, and `rollback_failed_start` never removes the
            # directory it rolled away from -- so once a version failed its
            # health check it could never be installed again, while `check()`
            # kept offering it. The user could retry forever: a fresh download
            # every time, the same error every time, and one line of UI.
            try:
                self._validate_app(final, manifest)
            except Exception:
                remove_tree(final)
            else:
                # Already here and healthy: adopt it instead of re-extracting.
                return self._point_at(manifest.version)
        staging.mkdir(parents=True)
        try:
            safe_extract_zip(archive_path, staging)
            self._validate_app(staging, manifest)
            os.replace(staging, final)
        except BaseException:
            remove_tree(staging)
            remove_tree(final)
            raise

        return self._point_at(manifest.version)

    def _point_at(self, version: str) -> PendingSwitch:
        current = self.read_pointer() if self.pointer_path.is_file() else {}
        previous = current.get("current")
        self.write_pointer(
            current=version,
            previous=previous if isinstance(previous, str) else None,
            pending_health=True,
        )
        return PendingSwitch(
            version=version,
            previous=previous if isinstance(previous, str) else None,
            pending_health=True,
        )

    def confirm_health(self, version: str) -> None:
        pointer = self.read_pointer()
        if pointer.get("current") != version:
            raise ValueError("Cannot confirm a version that is not current")
        version_dir = self.paths.app_versions / version
        validate_app_directory(version_dir, version=version)
        self.write_pointer(
            current=version,
            previous=(
                pointer.get("previous")
                if isinstance(pointer.get("previous"), str)
                else None
            ),
            pending_health=False,
            health_attempts=0,
        )

    def prepare_startup(self) -> str | None:
        if not self.pointer_path.is_file():
            return None
        pointer = self.read_pointer()
        current = pointer.get("current")
        if not isinstance(current, str) or not current:
            return None
        if not pointer.get("pendingHealth"):
            return current
        attempts = pointer.get("healthAttempts", 0)
        if not isinstance(attempts, int) or attempts < 0:
            attempts = 0
        if attempts >= 1:
            return self.rollback_failed_start() or current
        previous = pointer.get("previous")
        self.write_pointer(
            current=current,
            previous=previous if isinstance(previous, str) else None,
            pending_health=True,
            health_attempts=1,
        )
        return current

    def rollback_failed_start(self) -> str | None:
        if not self.pointer_path.is_file():
            return None
        pointer = self.read_pointer()
        if not pointer.get("pendingHealth"):
            return None
        current = pointer.get("current")
        previous = pointer.get("previous")
        if not isinstance(previous, str) or not previous:
            return None
        self.write_pointer(
            current=previous,
            previous=current if isinstance(current, str) else None,
            pending_health=False,
            health_attempts=0,
        )
        return previous

    def read_pointer(self) -> dict[str, object]:
        body = json.loads(self.pointer_path.read_text(encoding="utf-8-sig"))
        if not isinstance(body, dict):
            raise ValueError("App pointer must be a JSON object")
        return body

    def write_pointer(
        self,
        *,
        current: str,
        previous: str | None,
        pending_health: bool,
        health_attempts: int = 0,
    ) -> None:
        self.pointer_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.pointer_path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {
                    "current": current,
                    "previous": previous,
                    "pendingHealth": pending_health,
                    "healthAttempts": health_attempts,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temp, self.pointer_path)

    @staticmethod
    def _verify_archive(archive_path: Path, manifest: UpdateManifest) -> None:
        asset = manifest.assets.app
        if archive_path.stat().st_size != asset.size:
            raise ValueError("App update archive size does not match the manifest")
        digest = hashlib.sha256()
        with archive_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != asset.sha256:
            raise ValueError("App update archive SHA-256 does not match the manifest")

    @staticmethod
    def _validate_app(staging: Path, manifest: UpdateManifest) -> None:
        validate_app_directory(
            staging, version=manifest.version, platform=manifest.platform
        )
