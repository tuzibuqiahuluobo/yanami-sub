from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_cloud_build_is_manual_read_only_and_reuses_the_release_scripts():
    workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "  push:" not in workflow and "  pull_request:" not in workflow
    assert "contents: read" in workflow and "contents: write" not in workflow
    for script in ("build-bootstrap.ps1", "build-installer.ps1", "build-release.ps1"):
        assert script in workflow
    assert "ref: v0.5.1" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "environment: release-build" in workflow
    assert "if: ${{ inputs.signed_updates }}" in workflow
    assert "Signing key does not match the shipped trust anchor" in workflow
    assert "Remove-Item -LiteralPath $KeyFile -Force" in workflow
    assert "gh release" not in workflow


def test_cloud_build_uploads_only_allowlisted_artifacts_not_the_workspace():
    workflow = (ROOT / ".github/workflows/build-windows.yml").read_text(encoding="utf-8")
    uploads = workflow.split("name: Downloadable build artifacts", 1)[1]
    assert "dist/installer/*.exe" in uploads
    assert "dist/portable/*.zip" in uploads
    assert "dist/release/*.sig" in uploads
    assert "RUNNER_TEMP" not in uploads and "*.pem" not in uploads
