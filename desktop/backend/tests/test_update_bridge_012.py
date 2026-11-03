import pytest
from packaging.version import Version
from desktop.backend.updates.manifest import LocalUpdateState, UpdateManifest, select_asset
from desktop.backend.updates.service import is_desktop_release, manifest_asset_names


def release(version, preview=False, suffix=""):
    return {"tag_name": f"v{version}", "prerelease": preview, "assets": [
        {"name": f"yanami-sub-update-manifest{suffix}.{extension}", "browser_download_url": "https://example.test"}
        for extension in ("json", "sig")]}


def test_old_rc79_discovers_stable_bridge_not_new_preview():
    stable = release("0.1.2")
    preview = release("0.1.3-rc.1", True, "-v2")
    legacy_names = {"yanami-sub-update-manifest.json", "yanami-sub-update-manifest.sig"}
    assert legacy_names <= {asset["name"] for asset in stable["assets"]}
    assert not legacy_names <= {asset["name"] for asset in preview["assets"]}
    assert is_desktop_release(stable, "stable")
    assert is_desktop_release(preview, "all")
    assert not is_desktop_release(preview, "stable")


def test_manifest_pair_is_complete_and_v2_preferred():
    names = {asset["name"]: "url" for asset in release("0.1.3", True, "-v2")["assets"]}
    assert manifest_asset_names(names)[0].endswith("-v2.json")
    with pytest.raises(KeyError):
        manifest_asset_names({"yanami-sub-update-manifest-v2.json": "url"})


@pytest.mark.parametrize("current,channel,target,preview", [
    ("0.1.2", "stable", "0.2.1", False),
    ("0.1.3-rc.1", "beta", "0.2.1", False),
    ("0.1.2", "stable", "0.2.2-rc.1", True),
    ("0.2.1", "stable", "0.2.2-rc.1", True),
])
def test_core060_releases_require_full_launcher_update(current, channel, target, preview):
    assert Version(current) < Version(target)
    asset = {"url": "https://example.test/update.zip", "size": 1, "sha256": "a" * 64}
    manifest = UpdateManifest.model_validate({
        "schemaVersion": 1, "keyId": "test", "version": target,
        "channel": "beta" if preview else "stable", "platform": "windows-x64",
        "prerelease": preview, "minimumLauncherVersion": target,
        "minimumSupportedVersion": "0.1.0-rc.3", "assets": {"app": asset, "full": asset},
    })
    local = LocalUpdateState(version=current, launcher_version=current, channel=channel, platform="windows-x64")
    assert select_asset(manifest, local, include_preview=preview) == "full"
    item = release(target, preview, "-v2" if preview else "")
    assert is_desktop_release(item, "stable") is not preview
    assert is_desktop_release(item, "all")
