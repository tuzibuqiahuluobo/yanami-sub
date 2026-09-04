from __future__ import annotations

import base64
from importlib import resources
import json
from pathlib import Path
import re
import subprocess
import tomllib

from packaging.version import Version


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_the_update_trust_anchor_is_tracked_and_real() -> None:
    relative = "desktop/resources/trusted-update-keys.json"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
    )
    assert tracked.returncode == 0, f"{relative} must be tracked by git"

    keys = json.loads(
        (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
    )["keys"]
    example = json.loads(
        (
            REPOSITORY_ROOT
            / "desktop"
            / "resources"
            / "trusted-update-keys.example.json"
        ).read_text(encoding="utf-8")
    )["keys"]
    assert keys, "the trust anchor lists no keys"
    placeholders = set(example.values())
    for key_id, encoded in keys.items():
        assert encoded not in placeholders, f"{key_id} still uses a placeholder key"
        assert len(base64.b64decode(encoded)) == 32


def test_no_workflow_builds_with_the_example_trust_anchor() -> None:
    workflow_root = REPOSITORY_ROOT / ".github" / "workflows"
    offenders = [
        workflow.name
        for workflow in workflow_root.glob("*.yml")
        if "-AllowExampleUpdateConfig" in workflow.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_desktop_extra_declares_every_direct_python_dependency() -> None:
    document = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = document["project"]["optional-dependencies"]["desktop"]
    names = {
        re.split(r"[<>=!~ ;\[]", dependency, maxsplit=1)[0].lower()
        for dependency in dependencies
    }
    assert names == {
        "cryptography",
        "httpx",
        "packaging",
        "pillow",
        "pydantic",
        "pystray",
        "pywebview",
    }

    development = document["project"]["optional-dependencies"]["dev"]
    development_names = {
        re.split(r"[<>=!~ ;\[]", dependency, maxsplit=1)[0].lower()
        for dependency in development
    }
    assert {"pillow", "pyinstaller", "pyinstaller-hooks-contrib"} <= (
        development_names
    )


def test_the_desktop_release_uses_one_version_number() -> None:
    project = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    frontend = json.loads(
        (
            REPOSITORY_ROOT / "desktop" / "frontend" / "package.json"
        ).read_text(encoding="utf-8")
    )
    launcher = json.loads(
        (
            REPOSITORY_ROOT / "desktop" / "resources" / "launcher.json"
        ).read_text(encoding="utf-8")
    )
    installer = (
        REPOSITORY_ROOT / "desktop" / "installer" / "FineSubDesktop.iss"
    ).read_text(encoding="utf-8")

    assert "version" in project["project"].get("dynamic", [])
    assert "version" not in project["project"]
    expected_text = (REPOSITORY_ROOT / "VERSION").read_text("utf-8").strip()
    expected = Version(expected_text)
    assert Version(frontend["version"]) == expected
    assert Version(launcher["appVersion"]) == expected
    assert Version(launcher["launcherVersion"]) == expected
    assert f'#define AppVersion "{expected_text}"' in installer


def test_release_defaults_do_not_promise_future_deltas() -> None:
    script = (
        REPOSITORY_ROOT / "desktop" / "scripts" / "build-release.ps1"
    ).read_text(encoding="utf-8")
    version = Version(
        (REPOSITORY_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    )

    assert "[string[]]$SupportedFrom = @()" in script
    for name in ("MinimumLauncherVersion", "MinimumSupportedVersion"):
        match = re.search(rf'\[string\]\${name} = "([^"]+)"', script)
        assert match is not None
        assert Version(match.group(1)) <= version


def test_upstream_runtime_keeps_the_verified_tuna_python_route() -> None:
    package = resources.files("finesub_bootstrap")
    sources = json.loads(
        package.joinpath("download-sources.json").read_text(encoding="utf-8")
    )
    mirror = sources["pypiIndex"]
    mainland_lock = package.joinpath("pylock.win-py312.cn.toml").read_text(
        encoding="utf-8"
    )

    assert mirror == "https://pypi.tuna.tsinghua.edu.cn/simple"
    assert "https://pypi.tuna.tsinghua.edu.cn/packages/" in mainland_lock
    assert "sha256 =" in mainland_lock
