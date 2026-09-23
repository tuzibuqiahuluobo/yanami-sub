from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from finesub_bootstrap.paths import AppPaths

from desktop.backend.resources.manual_wheels import (
    DesktopRuntimeEnvironment,
    failed_wheel,
)


FILENAME = "ctranslate2-4.8.1+finesub0.4.0.cu128-cp312-cp312-win_amd64.whl"
URL = f"https://github.com/caca2331/finesub/releases/download/ct2/{FILENAME}"


def _lock(tmp_path: Path, digest: str) -> Path:
    lock = tmp_path / "pylock.win-py312.toml"
    lock.write_text(
        'lock-version = "1.0"\ncreated-by = "uv"\nrequires-python = ">=3.12"\n'
        f'[[packages]]\nname = "ctranslate2"\nversion = "4.8.1"\n'
        f'archive = {{ url = "{URL}", hashes = {{ sha256 = "{digest}" }} }}\n',
        encoding="utf-8",
    )
    return lock


def test_failed_locked_wheel_can_be_guided_into_verified_local_retry(
    tmp_path: Path,
) -> None:
    content = b"test-wheel-bytes"
    lock = _lock(tmp_path, hashlib.sha256(content).hexdigest())
    error = subprocess.CalledProcessError(
        2, ["uv", "pip", "install"], output=f"Failed to install: {FILENAME}"
    )
    assert failed_wheel(lock, error).url == URL

    paths = AppPaths.for_root(tmp_path)
    local = paths.cache / "downloads" / FILENAME
    local.parent.mkdir(parents=True)
    local.write_bytes(content)
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def runner(command, *, cwd, env, check):
        commands.append(command)
        environments.append(env)
        assert Path(command[-1]).read_text(encoding="utf-8").count(
            local.resolve().as_uri()
        ) == 1
        assert URL not in Path(command[-1]).read_text(encoding="utf-8")

    runtime = DesktopRuntimeEnvironment(
        paths=paths,
        app_source=tmp_path,
        runtime_lock=lock,
        uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    logs: list[str] = []
    runtime._run(
        ["uv", "pip", "install", "--requirement", str(lock)],
        {},
        log=logs.append,
        should_pause=None,
    )

    assert commands and "使用已校验的本地依赖" in logs[0]
    assert environments[0]["UV_HTTP_TIMEOUT"] == "120"
    assert environments[0]["UV_HTTP_RETRIES"] == "5"
    assert runtime.runtime_lock == lock
    assert not Path(commands[0][-1]).exists()


def test_wrong_hash_keeps_original_lock_and_user_network_settings(tmp_path: Path) -> None:
    lock = _lock(tmp_path, hashlib.sha256(b"correct").hexdigest())
    paths = AppPaths.for_root(tmp_path)
    local = paths.cache / "downloads" / FILENAME
    local.parent.mkdir(parents=True)
    local.write_bytes(b"wrong")
    seen: list[tuple[list[str], dict[str, str]]] = []

    def runner(command, *, cwd, env, check):
        seen.append((command, env))

    runtime = DesktopRuntimeEnvironment(
        paths=paths,
        app_source=tmp_path,
        runtime_lock=lock,
        uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    logs: list[str] = []
    runtime._run(
        ["uv", "pip", "install", "--requirement", str(lock)],
        {"UV_HTTP_TIMEOUT": "240", "UV_HTTP_RETRIES": "1"},
        log=logs.append,
        should_pause=None,
    )

    assert seen[0][0][-1] == str(lock)
    assert seen[0][1]["UV_HTTP_TIMEOUT"] == "240"
    assert seen[0][1]["UV_HTTP_RETRIES"] == "1"
    assert "SHA-256 不匹配" in logs[0]
