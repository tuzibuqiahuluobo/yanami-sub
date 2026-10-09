import pytest
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
