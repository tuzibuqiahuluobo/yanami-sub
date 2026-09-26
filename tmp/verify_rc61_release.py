from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from desktop.backend.updates.manifest import verify_manifest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0-rc.6.post1"
release = ROOT / "dist" / "release"
installer = ROOT / "dist" / "installer" / f"Yanami-Sub-{VERSION}-Setup.exe"

manifest_path = release / "yanami-sub-update-manifest.json"
signature_path = release / "yanami-sub-update-manifest.sig"
trusted = json.loads(
    (ROOT / "desktop" / "resources" / "trusted-update-keys.json").read_text(
        encoding="utf-8"
    )
)["keys"]
manifest = verify_manifest(
    manifest_path.read_bytes(),
    signature_path.read_bytes(),
    trusted,
    expected_channel="beta",
)
assert manifest.version == VERSION
assert manifest.prerelease is True
assert manifest.draft is False
assert manifest.minimum_launcher_version == "0.1.0-rc.5"
assert manifest.minimum_supported_version == "0.1.0-rc.5"
assert manifest.assets.app.supported_from == []
assert "RC6.1" in manifest.release_notes


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


artifacts: dict[str, dict[str, object]] = {}
for kind, asset in (("app", manifest.assets.app), ("full", manifest.assets.full)):
    path = release / asset.url.rsplit("/", 1)[-1]
    assert path.is_file()
    assert path.stat().st_size == asset.size
    assert sha256(path) == asset.sha256
    checksum = path.with_name(path.name + ".sha256")
    assert checksum.read_text(encoding="ascii").split()[0] == asset.sha256
    artifacts[kind] = {"name": path.name, "size": path.stat().st_size}

app_zip = release / f"yanami-sub-app-{VERSION}-win-x64.zip"
with zipfile.ZipFile(app_zip) as archive:
    names = set(archive.namelist())
    assert "desktop/backend/settings/local_agents.py" in names
    assert "desktop/frontend/out/index.html" in names

full_zip = release / f"yanami-sub-full-{VERSION}-win-x64.zip"
with zipfile.ZipFile(full_zip) as archive:
    names = set(archive.namelist())
    assert "Yanami Sub.exe" in names
    assert f"app/versions/{VERSION}/desktop/frontend/out/index.html" in names
    assert not any(
        Path(name).name.lower() in {"finesub.exe", "finesub desktop.exe"}
        for name in names
    )
    pointer = json.loads(archive.read("app/current.json"))
    assert pointer["current"] == VERSION

assert installer.is_file()
installer_hash = sha256(installer)
installer_checksum = installer.with_name(installer.name + ".sha256")
assert installer_checksum.read_text(encoding="ascii").split()[0] == installer_hash
artifacts["installer"] = {"name": installer.name, "size": installer.stat().st_size}

print(
    json.dumps(
        {
            "version": manifest.version,
            "keyId": manifest.key_id,
            "channel": manifest.channel,
            "artifacts": artifacts,
        },
        ensure_ascii=False,
        indent=2,
    )
)
