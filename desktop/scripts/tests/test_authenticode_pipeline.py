from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
AUTHENTICODE = REPO_ROOT / "desktop" / "scripts" / "authenticode.ps1"
BUILD_RELEASE = REPO_ROOT / "desktop" / "scripts" / "build-release.ps1"


def test_authenticode_certificate_is_fail_closed_and_publisher_bound() -> None:
    script = AUTHENTICODE.read_text(encoding="utf-8")

    assert 'YanamiSubExpectedPublisher = "tuzibuqiahuluobo"' in script
    assert 'YanamiSubCodeSigningOid = "1.3.6.1.5.5.7.3.3"' in script
    assert "YANAMI_SUB_AUTHENTICODE_PFX" in script
    assert "YANAMI_SUB_AUTHENTICODE_PASSWORD" in script
    assert "YANAMI_SUB_AUTHENTICODE_THUMBPRINT" in script
    assert "$Certificate.HasPrivateKey" in script
    assert "$Chain.Build($Certificate)" in script
    assert '$Result.Status -ne "Valid"' in script
    assert '$Verified.Status -ne "Valid"' in script
    assert '"Yanami Sub.exe"' in script
    assert '"updater\\Yanami Sub Updater.exe"' in script
    assert "Packaged executable required for Authenticode signing was not found" in script


def test_release_archives_contain_signed_executables_when_signing_is_required() -> None:
    script = BUILD_RELEASE.read_text(encoding="utf-8")

    assert "[switch]$RequireAuthenticode" in script
    signing = script.index("Set-YanamiSubAuthenticodeSignature")
    app_source = script.index("$AppSource =")
    release_builder = script.index('$Arguments = @(')
    assert signing < app_source < release_builder
