from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest

from finesub_bootstrap.paths import AppPaths
from finesub_bootstrap.downloader import DownloadPaused

from desktop.backend.resources.manual_wheels import (
    DesktopRuntimeEnvironment,
    _sample_wheel,
    failed_wheel,
    install_lock_name,
    local_lock,
)
from desktop.backend.resources.desktop_service import DesktopResourceService


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


def _torch_locks(tmp_path: Path) -> tuple[Path, Path]:
    official = tmp_path / "pylock.win-py312.toml"
    mirror = tmp_path / "pylock.win-py312.cn.toml"
    content = (
        'lock-version = "1.0"\ncreated-by = "uv"\nrequires-python = ">=3.12"\n'
        '[[packages]]\nname = "torch"\nversion = "2.11.0"\n'
        'archive = { url = "https://{host}/torch-2.11.0-cp312-win_amd64.whl", '
        'hashes = { sha256 = "' + "0" * 64 + '" } }\n'
        '[[packages]]\nname = "click"\nversion = "8.4.2"\n'
        'archive = { url = "https://{pypi}/click-8.4.2-py3-none-any.whl", '
        'hashes = { sha256 = "' + "0" * 64 + '" } }\n'
    )
    official.write_text(
        content.replace("{host}", "official.example.org").replace(
            "{pypi}", "files.pythonhosted.org"
        ),
        encoding="utf-8",
    )
    mirror.write_text(
        content.replace("{host}", "mirror.example.org").replace(
            "{pypi}", "pypi.tuna.tsinghua.edu.cn"
        ),
        encoding="utf-8",
    )
    return official, mirror


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


def test_cn_lock_uses_valid_pep751_filename_without_changing_lock_bytes(
    tmp_path: Path,
) -> None:
    canonical = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    cn_lock = canonical.with_name("pylock.win-py312.cn.toml")
    cn_lock.write_bytes(canonical.read_bytes())
    paths = AppPaths.for_root(tmp_path)
    with local_lock(cn_lock, paths.cache, None) as effective:
        assert effective.name == install_lock_name(cn_lock) == "pylock.win-py312-cn.toml"
        assert effective.read_bytes() == cn_lock.read_bytes()
    assert not effective.exists()


def test_manual_guidance_recognises_the_temporary_cn_lock_name(tmp_path: Path) -> None:
    canonical = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    cn_lock = canonical.with_name("pylock.win-py312.cn.toml")
    cn_lock.write_text(
        canonical.read_text(encoding="utf-8").replace(
            "https://github.com/caca2331/finesub/",
            "https://mirror.example.org/finesub/",
        ),
        encoding="utf-8",
    )
    paths = AppPaths.for_root(tmp_path)
    service = DesktopResourceService(
        bootstrap=object(),
        runtime=SimpleNamespace(runtime_lock=canonical, paths=paths),
        system_tool_finders={}, local_reuse=object(),
    )
    error = subprocess.CalledProcessError(
        1,
        ["uv", "pip", "install", "--requirement", str(tmp_path / install_lock_name(cn_lock))],
        output=f"Failed to install: {FILENAME}",
    )
    guidance = service.manual_download("uv", error)
    assert guidance is not None
    assert guidance["url"].startswith("https://mirror.example.org/")


def test_network_failure_retries_direct_without_proxy_credentials(tmp_path: Path) -> None:
    lock = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    seen: list[dict[str, str]] = []

    def runner(command, *, cwd, env, check):
        seen.append(env)
        if len(seen) == 1:
            raise subprocess.CalledProcessError(
                1, command, output="network connection timed out"
            )

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=lock, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    logs: list[str] = []
    runtime._run(
        ["uv", "pip", "install", "--requirement", str(lock)],
        {"HTTPS_PROXY": "http://secret@example.org:8080"},
        log=logs.append, should_pause=None,
    )
    assert len(seen) == 2
    assert "HTTPS_PROXY" in seen[0]
    assert not any(key.lower().endswith("_proxy") for key in seen[1])
    assert any("改为直连" in line for line in logs)
    assert all("secret" not in line for line in logs)


@pytest.mark.parametrize("failure", ["permission denied", "hash mismatch"])
def test_proxy_retry_does_not_repeat_local_or_integrity_failure(
    tmp_path: Path, failure: str,
) -> None:
    lock = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    attempts = 0

    def runner(command, *, cwd, env, check):
        nonlocal attempts
        attempts += 1
        raise subprocess.CalledProcessError(1, command, output=failure)

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=lock, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    with pytest.raises(subprocess.CalledProcessError):
        runtime._run(
            ["uv", "pip", "install", "--requirement", str(lock)],
            {"HTTPS_PROXY": "http://proxy.example.org:8080"},
            log=None, should_pause=None,
        )
    assert attempts == 1


def test_auto_global_network_failure_retries_existing_cn_lock(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("FINESUB_DOWNLOAD_REGION", raising=False)
    lock = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    cn_lock = lock.with_name("pylock.win-py312.cn.toml")
    cn_lock.write_text(lock.read_text(encoding="utf-8"), encoding="utf-8")
    seen: list[Path] = []

    def runner(command, *, cwd, env, check):
        seen.append(Path(command[-1]))
        if len(seen) == 1:
            raise subprocess.CalledProcessError(1, command, output="network timed out")

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=lock, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: None)
    logs: list[str] = []
    runtime._install_dependencies(
        tmp_path / "uv.exe", tmp_path / "python.exe", {},
        log=logs.append, should_pause=None,
    )
    assert seen[0] == lock
    assert seen[1].name == install_lock_name(cn_lock)
    assert any("国内镜像" in line for line in logs)


def test_auto_prefers_clearly_faster_torch_host_without_downloading_wheel(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("FINESUB_DOWNLOAD_REGION", raising=False)
    official, mirror = _torch_locks(tmp_path)
    sampled: list[str] = []

    def sample(url, proxy, should_pause):
        sampled.append(url)
        return 300_000 if "mirror.example.org" in url else 50_000

    monkeypatch.setattr(
        "desktop.backend.resources.manual_wheels._sample_wheel", sample
    )
    seen: list[str] = []

    def runner(command, *, cwd, env, check):
        seen.append(Path(command[-1]).name)

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=official, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: None)
    logs: list[str] = []
    runtime._install_dependencies(
        tmp_path / "uv.exe", tmp_path / "python.exe", {},
        log=logs.append, should_pause=None,
    )
    assert len(sampled) == 3
    assert seen == [install_lock_name(mirror)]
    assert any("短连接测试优先：国内镜像" in line for line in logs)


def test_fast_pytorch_mirror_does_not_hide_blocked_pypi_mirror(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("FINESUB_DOWNLOAD_REGION", raising=False)
    official, _ = _torch_locks(tmp_path)

    def sample(url, proxy, should_pause):
        if "pypi.tuna.tsinghua.edu.cn" in url:
            return None
        return 300_000 if "mirror.example.org" in url else 50_000

    monkeypatch.setattr(
        "desktop.backend.resources.manual_wheels._sample_wheel", sample
    )
    seen: list[str] = []

    def runner(command, *, cwd, env, check):
        seen.append(Path(command[-1]).name)

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=official, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: None)
    runtime._install_dependencies(
        tmp_path / "uv.exe", tmp_path / "python.exe", {},
        log=None, should_pause=None,
    )
    assert seen == [official.name]


def test_forced_source_skips_speed_probe(tmp_path: Path, monkeypatch) -> None:
    official, _ = _torch_locks(tmp_path)
    monkeypatch.setenv("FINESUB_DOWNLOAD_REGION", "global")
    monkeypatch.setattr(
        "desktop.backend.resources.manual_wheels._sample_wheel",
        lambda *args: pytest.fail("forced source must not be probed"),
    )
    seen: list[str] = []

    def runner(command, *, cwd, env, check):
        seen.append(Path(command[-1]).name)

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=official, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: None)
    runtime._install_dependencies(
        tmp_path / "uv.exe", tmp_path / "python.exe", {},
        log=None, should_pause=None,
    )
    assert seen == [official.name]


def test_local_torch_candidate_skips_unneeded_network_probe(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("FINESUB_DOWNLOAD_REGION", raising=False)
    official, _ = _torch_locks(tmp_path)
    paths = AppPaths.for_root(tmp_path)
    local = paths.cache / "downloads" / "torch-2.11.0-cp312-win_amd64.whl"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"candidate")
    monkeypatch.setattr(
        "desktop.backend.resources.manual_wheels._sample_wheel",
        lambda *args: pytest.fail("local candidate should be checked first"),
    )
    seen: list[str] = []

    def runner(command, *, cwd, env, check):
        seen.append(Path(command[-1]).name)

    runtime = DesktopRuntimeEnvironment(
        paths=paths, app_source=tmp_path, runtime_lock=official,
        uv_executable=lambda: tmp_path / "uv.exe", command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: None)
    runtime._install_dependencies(
        tmp_path / "uv.exe", tmp_path / "python.exe", {},
        log=None, should_pause=None,
    )
    assert seen == [official.name]


def test_speed_probe_reads_at_most_256_kib_and_obeys_pause(monkeypatch) -> None:
    chunks = 0
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, *, chunk_size):
            nonlocal chunks
            assert chunk_size == 64 * 1024
            for _ in range(100):
                chunks += 1
                yield b"x" * chunk_size

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url, *, headers):
            observed.update(method=method, url=url, headers=headers)
            return Response()

    def make_client(route, *, timeout):
        observed["proxy"] = route.proxy
        return Client()

    monkeypatch.setattr(
        "desktop.backend.resources.manual_wheels.create_client", make_client
    )
    speed = _sample_wheel(
        "https://example.org/torch.whl", "http://proxy.example.org:8080", None
    )
    assert speed is not None and speed > 0
    assert chunks == 4
    assert observed["headers"]["Range"] == "bytes=0-262143"
    assert observed["proxy"] == "http://proxy.example.org:8080"
    with pytest.raises(DownloadPaused):
        _sample_wheel("https://example.org/torch.whl", None, lambda: True)
    assert chunks == 4
    def missing_proxy_client(*args, **kwargs):
        raise ImportError("socksio")

    monkeypatch.setattr(
        "desktop.backend.resources.manual_wheels.create_client",
        missing_proxy_client,
    )
    assert _sample_wheel("https://example.org/torch.whl", None, None) is None


def test_forced_global_does_not_retry_cn(
    tmp_path: Path, monkeypatch,
) -> None:
    lock = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    lock.with_name("pylock.win-py312.cn.toml").write_text(
        lock.read_text(encoding="utf-8"), encoding="utf-8"
    )
    seen: list[list[str]] = []

    def runner(command, *, cwd, env, check):
        seen.append(command)
        raise subprocess.CalledProcessError(1, command, output="network timed out")

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=lock, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: None)
    monkeypatch.setenv("FINESUB_DOWNLOAD_REGION", "global")
    with pytest.raises(subprocess.CalledProcessError):
        runtime._install_dependencies(
            tmp_path / "uv.exe", tmp_path / "python.exe", {},
            log=None, should_pause=None,
        )
    assert len(seen) == 1


def test_auto_does_not_switch_sources_for_local_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("FINESUB_DOWNLOAD_REGION", raising=False)
    lock = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    lock.with_name("pylock.win-py312.cn.toml").write_text(
        lock.read_text(encoding="utf-8"), encoding="utf-8"
    )
    attempts = 0

    def runner(command, *, cwd, env, check):
        nonlocal attempts
        attempts += 1
        raise subprocess.CalledProcessError(
            1, command, output="network connection failed; disk permission denied"
        )

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=lock, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: None)
    with pytest.raises(subprocess.CalledProcessError):
        runtime._install_dependencies(
            tmp_path / "uv.exe", tmp_path / "python.exe", {},
            log=None, should_pause=None,
        )
    assert attempts == 1


def test_cn_mirror_integrity_failure_falls_back_to_official(
    tmp_path: Path, monkeypatch,
) -> None:
    lock = _lock(tmp_path, hashlib.sha256(b"wheel").hexdigest())
    cn_lock = lock.with_name("pylock.win-py312.cn.toml")
    cn_lock.write_text(lock.read_text(encoding="utf-8"), encoding="utf-8")
    attempts: list[Path] = []

    def runner(command, *, cwd, env, check):
        attempts.append(Path(command[-1]))
        if len(attempts) == 1:
            raise subprocess.CalledProcessError(1, command, output="hash mismatch")

    runtime = DesktopRuntimeEnvironment(
        paths=AppPaths.for_root(tmp_path), app_source=tmp_path,
        runtime_lock=lock, uv_executable=lambda: tmp_path / "uv.exe",
        command_runner=runner,
    )
    monkeypatch.setattr(runtime, "regional_lock", lambda: cn_lock)
    runtime._install_dependencies(
        tmp_path / "uv.exe", tmp_path / "python.exe", {},
        log=None, should_pause=None,
    )
    assert attempts[0].name == install_lock_name(cn_lock)
    assert attempts[1] == lock
