import base64
import hashlib
from pathlib import Path

import pytest

from desktop.backend.resources.runtime_integrity import check_runtime


def _digest(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


@pytest.fixture
def overlap(tmp_path):
    site = tmp_path / "site-packages"
    (site / "onnx").mkdir(parents=True)
    lock = tmp_path / "pylock.toml"
    lock.write_text('lock-version = "1.0"\n[[packages]]\nname = "onnx"\nversion = "1.23.2"\n'
                    '[[packages]]\nname = "onnx-weekly"\nversion = "1.23.0.dev20260805"\n', encoding="utf-8")
    for name, version, content in (("onnx", "1.23.2", b"stable"), ("onnx_weekly", "1.23.0.dev20260805", b"weekly")):
        info = site / f"{name}-{version}.dist-info"
        info.mkdir()
        (info / "RECORD").write_text("".join(f"onnx/{path},{_digest(content)},6\n" for path in ("__init__.py", "_mapping.py")), encoding="utf-8")
    return site, lock


@pytest.mark.parametrize("content", [b"stable", b"weekly"])
def test_either_complete_pinned_owner_is_valid(overlap, content):
    site, lock = overlap
    for name in ("__init__.py", "_mapping.py"):
        (site / "onnx" / name).write_bytes(content)
    assert not check_runtime(site, lock, verify_hashes=True).mismatched


@pytest.mark.parametrize("contents", [(b"stable", b"weekly"), (b"tampered", b"weekly"), (None, b"weekly")])
def test_mixed_corrupt_or_missing_namespace_is_not_accepted(overlap, contents):
    site, lock = overlap
    for name, content in zip(("__init__.py", "_mapping.py"), contents):
        if content is not None:
            (site / "onnx" / name).write_bytes(content)
    assert check_runtime(site, lock, verify_hashes=True).mismatched


def test_nonshared_damage_remains_visible(overlap):
    site, lock = overlap
    for name in ("__init__.py", "_mapping.py"):
        (site / "onnx" / name).write_bytes(b"weekly")
    info = site / "onnx-1.23.2.dist-info" / "RECORD"
    with info.open("a", encoding="utf-8") as stream:
        stream.write(f"onnx-private.bin,{_digest(b'original')},8\n")
    (site / "onnx-private.bin").write_bytes(b"tampered")
    report = check_runtime(site, lock, verify_hashes=True)
    assert report.hash_mismatches == {"onnx": ["onnx-private.bin"]}


def test_wrong_distribution_version_is_not_accepted(overlap):
    site, lock = overlap
    (site / "onnx-1.23.2.dist-info").rename(site / "onnx-0.1.dist-info")
    assert check_runtime(site, lock, verify_hashes=True).mismatched
