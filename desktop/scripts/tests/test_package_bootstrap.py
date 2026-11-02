from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "desktop" / "scripts" / "package-bootstrap.ps1"


def test_package_bootstrap_excludes_tests_and_keeps_runtime_sources(tmp_path: Path) -> None:
    work = tmp_path / "package-bootstrap"
    fixture_repo = work / "repo"
    fixture_core = work / "core"
    output = work / "output"
    launcher_dist = output / "Yanami Sub.dist"
    try:
        (fixture_repo / "src" / "finesub").mkdir(parents=True)
        (fixture_repo / "src" / "finesub" / "pipeline.py").write_text(
            "PIPELINE = True\n", "utf-8"
        )
        (fixture_repo / "desktop" / "backend" / "launcher").mkdir(parents=True)
        (fixture_repo / "desktop" / "backend" / "launcher" / "main.py").write_text(
            "MAIN = True\n", "utf-8"
        )
        (fixture_repo / "desktop" / "backend" / "tests").mkdir(parents=True)
        (fixture_repo / "desktop" / "backend" / "tests" / "must_not_ship.py").write_text(
            "raise RuntimeError\n", "utf-8"
        )
        (fixture_repo / "desktop" / "backend" / "__pycache__").mkdir(parents=True)
        (fixture_repo / "desktop" / "backend" / "__pycache__" / "cache.pyc").write_bytes(
            b"cache"
        )
        (fixture_repo / "desktop" / "resources").mkdir(parents=True)
        (fixture_repo / "desktop" / "resources" / "manifest.json").write_text(
            "{}\n", "utf-8"
        )
        socksio_wheel = (
            fixture_repo
            / "desktop"
            / "resources"
            / "wheels"
            / "socksio-1.0.0-py3-none-any.whl"
        )
        socksio_wheel.parent.mkdir(parents=True)
        socksio_wheel.write_bytes(b"wheel fixture")
        # A tracked non-.py file under `src/`: the payload has to carry it,
        # and since the desktop split the runtime lock is exactly that --
        # the launcher reads it out of the app snapshot it installs.
        (
            fixture_repo
            / "src"
            / "finesub_bootstrap"
        ).mkdir(parents=True)
        (
            fixture_repo
            / "src"
            / "finesub_bootstrap"
            / "pylock.win-py312.toml"
        ).write_text('lock-version = "1.0"\n', "utf-8")
        (fixture_repo / "desktop" / "frontend" / "out").mkdir(parents=True)
        (fixture_repo / "desktop" / "frontend" / "out" / "index.html").write_text(
            "<main>FineSub</main>\n", "utf-8"
        )
        (fixture_repo / "desktop" / "__init__.py").write_text("", "utf-8")
        (fixture_repo / "pyproject.toml").write_text('[project]\nname="fixture"\ndependencies=["finesub==0.6.0"]\n', "utf-8")
        bootstrap = fixture_repo / "src" / "finesub_bootstrap"
        for name in ("environment.py", "runtime-manifest.json", "model-manifest.json", "download-sources.json", "pylock.win-py312.cn.toml"):
            (bootstrap / name).write_text("{}\n", "utf-8")
        shutil.copytree(fixture_repo / "src", fixture_core / "src")
        (fixture_core / "VERSION").write_text("0.6.0\n", "utf-8")
        for arguments in (
            ("init", "-q"), ("add", "-A"),
            ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "core"),
        ):
            subprocess.run(["git", *arguments], cwd=fixture_core, check=True, capture_output=True)
        core_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=fixture_core, text=True).strip()
        (fixture_repo / "desktop/resources/core-source.json").write_text(json.dumps({
            "repository": "fixture/core", "tag": "v0.6.0", "version": "0.6.0", "commit": core_commit,
        }), "utf-8")

        # Packaging is driven by `git ls-files` now, so the fixture has to be a
        # real repository -- and the untracked files below are the point: they
        # are exactly what used to ride along into a signed public zip.
        (fixture_repo / "src" / "leftover.log").write_text(
            "real API responses\n", "utf-8"
        )
        (fixture_repo / "src" / "scratch").mkdir(parents=True, exist_ok=True)
        (fixture_repo / "src" / "scratch" / "notes.py").write_text("X = 1\n", "utf-8")
        (fixture_repo / ".gitignore").write_text("*.log\nscratch/\n", "utf-8")
        for arguments in (
            ("init", "-q"),
            ("add", "-A"),
            ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "fixture"),
        ):
            subprocess.run(
                ["git", *arguments],
                cwd=fixture_repo,
                check=True,
                capture_output=True,
            )

        launcher_config = fixture_repo / "launcher.json"
        launcher_config.write_text(
            json.dumps(
                {
                    "appVersion": "0.0.0",
                    "launcherVersion": "0.0.0",
                    "channel": "stable",
                }
            ),
            "utf-8",
        )
        trusted_keys = fixture_repo / "trusted-update-keys.json"
        trusted_keys.write_text('{"keys":[]}\n', "utf-8")

        launcher_dist.mkdir(parents=True)
        (launcher_dist / "Yanami Sub.exe").write_bytes(b"launcher")

        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-RepoRoot",
                str(fixture_repo),
                "-CoreRoot",
                str(fixture_core),
                "-OutputDirectory",
                str(output),
                "-Version",
                "2.3.4",
                "-LauncherConfigPath",
                str(launcher_config),
                "-TrustedKeysPath",
                str(trusted_keys),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0, result.stderr

        version_root = launcher_dist / "app" / "versions" / "2.3.4"
        assert (version_root / "VERSION").read_text("utf-8").strip() == "2.3.4"
        assert (version_root / "src" / "finesub" / "pipeline.py").is_file()
        # Pre-0.4.0 launchers in the field validate payloads and locate the
        # active app source by this exact path; dropping it kills every in-app
        # update from 0.3.x (found in the 0.4.0 release rehearsal).
        legacy_stub = version_root / "src" / "asr_playground" / "pipeline.py"
        assert legacy_stub.is_file()
        assert "renamed to finesub" in legacy_stub.read_text("utf-8")
        # Untracked leftovers must not ship: invisible to `git status`, to the
        # CI gate and to review, but previously copied into the release zip.
        assert not (version_root / "src" / "leftover.log").exists()
        assert not (version_root / "src" / "scratch").exists()
        assert (version_root / "desktop" / "backend" / "launcher" / "main.py").is_file()
        manifest = json.loads((version_root / "app-manifest.json").read_text("utf-8"))
        expected_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=fixture_repo, text=True
        ).strip()
        assert manifest["sourceCommit"] == expected_commit
        assert manifest["coreCommit"] == core_commit
        assert manifest["coreVersion"] == "0.6.0"
        assert "desktop/backend/launcher/main.py" in manifest["files"]
        assert not (version_root / "desktop" / "backend" / "tests").exists()
        assert not (version_root / "desktop" / "backend" / "__pycache__").exists()
        assert (
            version_root
            / "src"
            / "finesub_bootstrap"
            / "pylock.win-py312.toml"
        ).is_file()
        assert (
            version_root
            / "desktop"
            / "resources"
            / "wheels"
            / socksio_wheel.name
        ).read_bytes() == b"wheel fixture"
        assert not (launcher_dist / "updater").exists()
        assert not (launcher_dist / "FineSub.exe").exists()
        # The split desktop package has one executable surface; command-line
        # behavior belongs to the separately installed upstream FineSub CLI.
        assert not (launcher_dist / "finesub.cmd").exists()
        assert not (launcher_dist / "finesub.py").exists()
        pointer = json.loads((launcher_dist / "app" / "current.json").read_text("utf-8-sig"))
        assert pointer["current"] == "2.3.4"
        assert not (launcher_dist / "app" / "current.json").read_bytes().startswith(
            b"\xef\xbb\xbf"
        )
        config = json.loads((launcher_dist / "launcher.json").read_text("utf-8-sig"))
        assert config["appVersion"] == "2.3.4"
        assert config["launcherVersion"] == "2.3.4"
        assert not (launcher_dist / "launcher.json").read_bytes().startswith(
            b"\xef\xbb\xbf"
        )
        checked = subprocess.run([
            "powershell.exe", "-NoProfile", "-Command",
            f"$ErrorActionPreference='Stop'; . '{SCRIPT.parent / 'source-tree.ps1'}'; "
            f"Assert-PackagedCoreSource -RepoRoot '{fixture_repo}' -VersionRoot '{version_root}'",
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert checked.returncode == 0, checked.stderr
    finally:
        shutil.rmtree(work, ignore_errors=True)
