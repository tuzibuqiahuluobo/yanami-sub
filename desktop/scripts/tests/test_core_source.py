from __future__ import annotations

import json
import hashlib
import ast
import sys
from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "desktop/scripts/source-tree.ps1"
REQUIRED = (
    "src/finesub/pipeline.py", "src/finesub_bootstrap/environment.py",
    "src/finesub_bootstrap/runtime-manifest.json", "src/finesub_bootstrap/model-manifest.json",
    "src/finesub_bootstrap/download-sources.json", "src/finesub_bootstrap/pylock.win-py312.toml",
    "src/finesub_bootstrap/pylock.win-py312.cn.toml",
)


def powershell(command):
    return subprocess.run(["powershell.exe", "-NoProfile", "-Command",
        f"$ErrorActionPreference='Stop'; . '{HELPER}'; {command}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def source(tmp_path):
    desktop, core = tmp_path / "desktop", tmp_path / "core"
    (desktop / "desktop/resources").mkdir(parents=True)
    (desktop / "pyproject.toml").write_text('[project]\ndependencies=["finesub==0.6.0"]\n', "utf-8")
    for name in REQUIRED:
        path = core / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# tracked\n", "utf-8")
    (core / "VERSION").write_text("0.6.0\n", "utf-8")
    git(core, "init", "-q")
    git(core, "add", "-A")
    git(core, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "core")
    pin = {"repository": "fixture/core", "tag": "v0.6.0", "version": "0.6.0", "commit": git(core, "rev-parse", "HEAD")}
    (desktop / "desktop/resources/core-source.json").write_text(json.dumps(pin), "utf-8")
    return desktop, core, pin


def test_every_build_caller_uses_the_same_exact_core_descriptor():
    pin = json.loads((ROOT / "desktop/resources/core-source.json").read_text("utf-8"))
    assert pin == {"repository": "caca2331/finesub", "tag": "v0.6.0", "version": "0.6.0",
                   "commit": "5caf422cbad36f0402c98eb565e4c29aee4ac197"}
    project = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    assert f'finesub=={pin["version"]}' in project["project"]["dependencies"]
    for workflow in ("ci.yml", "build-windows.yml"):
        text = (ROOT / ".github/workflows" / workflow).read_text("utf-8")
        assert "ref: ${{ steps.core.outputs.commit }}" in text
        assert "desktop/resources/core-source.json" in text
        assert text.index("Get-VerifiedCoreSource") < text.index("pip install")
        assert "ref: v0.5.1" not in text
    for script in ("build-bootstrap.ps1", "package-bootstrap.ps1", "setup-dev.ps1"):
        assert "Get-VerifiedCoreSource" in (ROOT / "desktop/scripts" / script).read_text("utf-8")
    for script in ("build-installer.ps1", "build-release.ps1"):
        assert "Assert-PackagedCoreSource" in (ROOT / "desktop/scripts" / script).read_text("utf-8")


def test_development_uv_bootstrap_preserves_the_desktop_transfer_fix():
    module = ast.parse((ROOT / "desktop/backend/launcher/main.py").read_text("utf-8"))
    versions = [ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "DESKTOP_UV_VERSION" for target in node.targets)]
    assert len(versions) == 1
    assert f'"uv=={versions[0]}"' in (ROOT / "desktop/scripts/setup-dev.ps1").read_text("utf-8")


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="PowerShell is required")
@pytest.mark.parametrize("damage", ["none", "version", "source"])
def test_build_python_must_load_the_verified_core_without_importing_it(tmp_path, damage):
    checkout = tmp_path / "checkout"
    library = checkout / "src"
    for name in ("finesub", "finesub_bootstrap"):
        package = library / name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("raise RuntimeError('must not import package')\n", "utf-8")
    metadata = library / "finesub-0.6.0.dist-info"
    metadata.mkdir()
    version = "0.5.1" if damage == "version" else "0.6.0"
    (metadata / "METADATA").write_text(f"Name: finesub\nVersion: {version}\n", "utf-8")
    expected = tmp_path / "other" if damage == "source" else checkout
    result = powershell(f"$env:PYTHONPATH='{library}'; Assert-PythonCoreSource -Python '{sys.executable}' "
                        f"-CoreSource ([pscustomobject]@{{Root='{expected}';Version='0.6.0'}})")
    assert (result.returncode == 0) == (damage == "none"), result.stderr


def test_build_identity_checks_precede_frontend_and_destructive_staging():
    script = (ROOT / "desktop/scripts/build-bootstrap.ps1").read_text("utf-8")
    assert script.index("Get-CleanSourceCommit -Path $RepoRoot") < script.index("Remove-BuildChild -Path $BuildChild")
    assert script.index("Assert-PythonCoreSource -Python $Python") < script.index("if (-not $SkipFrontend)")


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="PowerShell is required")
def test_core_verification_accepts_clean_pinned_source_and_ignores_untracked_files(source):
    desktop, core, pin = source
    (core / "src/finesub_bootstrap/private.py").write_text("PRIVATE=True\n", "utf-8")
    result = powershell(f"Get-VerifiedCoreSource -RepoRoot '{desktop}' -CoreRoot '{core}' | ConvertTo-Json -Compress")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["Commit"] == pin["commit"]
    output = core.parent / "stage"
    result = powershell(f"Copy-TrackedTree -RepoRoot '{core}' -RelativeRoot 'src/finesub_bootstrap' -Destination '{output}' -PythonOnly")
    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in output.iterdir()) == ["environment.py"]


@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="PowerShell is required")
@pytest.mark.parametrize("damage", ["wrong-commit", "dirty-lock", "wrong-version", "missing-lock", "dependency"])
def test_invalid_core_is_rejected_before_any_build_or_install(source, damage):
    desktop, core, pin = source
    if damage == "wrong-commit":
        pin["commit"] = "1" * 40
        (desktop / "desktop/resources/core-source.json").write_text(json.dumps(pin), "utf-8")
    elif damage == "dependency":
        (desktop / "pyproject.toml").write_text('dependencies=["finesub==0.5.1"]', "utf-8")
    elif damage == "wrong-version":
        git(core, "update-index", "--skip-worktree", "VERSION")
        (core / "VERSION").write_text("0.5.1\n", "utf-8")
    elif damage == "missing-lock":
        git(core, "update-index", "--skip-worktree", REQUIRED[-1])
        (core / REQUIRED[-1]).unlink()
    else:
        (core / REQUIRED[-1]).write_text("modified lock\n", "utf-8")
    result = powershell(f"Get-VerifiedCoreSource -RepoRoot '{desktop}' -CoreRoot '{core}'")
    assert result.returncode != 0
    assert not (desktop / ".venv-desktop").exists()


@pytest.mark.parametrize("damage", ["foreign-core", "missing-receipt", "changed-lock", None])
@pytest.mark.skipif(not shutil.which("powershell.exe"), reason="PowerShell is required")
def test_reused_packages_require_core_receipts_and_hashes(tmp_path, damage):
    pin = json.loads((ROOT / "desktop/resources/core-source.json").read_text("utf-8"))
    payload = tmp_path / "payload"
    payload.mkdir()
    body = {"version": "0.1.3-rc.1", "coreVersion": pin["version"], "coreCommit": pin["commit"], "files": {}}
    for name in ("VERSION", "desktop/resources/core-source.json", *REQUIRED[2:]):
        path = payload / name
        path.parent.mkdir(parents=True, exist_ok=True)
        contents = json.dumps(pin).encode() if name.endswith("core-source.json") else b"0.1.3-rc.1\n" if name == "VERSION" else b"locked input\n"
        path.write_bytes(contents)
        body["files"][name] = {"sha256": hashlib.sha256(contents).hexdigest()}
    if damage == "foreign-core":
        body["coreCommit"] = "f" * 40
    elif damage == "changed-lock":
        (payload / REQUIRED[-1]).write_bytes(b"different lock\n")
    if damage != "missing-receipt":
        (payload / "app-manifest.json").write_text(json.dumps(body), "utf-8")
    command = f"Assert-PackagedCoreSource -RepoRoot '{ROOT}' -VersionRoot '{payload}'"
    result = powershell(command)
    if damage is None:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
    if damage == "changed-lock":
        assert "Packaged core input differs" in result.stderr


def test_packaged_hashing_does_not_depend_on_hash_cmdlet_autoload():
    helper = HELPER.read_text("utf-8")
    assert "Get-FileHash" not in helper
    assert "[System.Security.Cryptography.SHA256]::Create()" in helper
    assert ".ComputeHash(" in helper
