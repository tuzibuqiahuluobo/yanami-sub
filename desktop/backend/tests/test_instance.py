from pathlib import Path
import os
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from desktop.backend.launcher.instance import InstanceGuard, instance_domain

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows desktop ownership")


def child(domain: Path, code: str):
    return subprocess.Popen(
        [sys.executable, "-u", "-c", (
            "from pathlib import Path; from desktop.backend.launcher.instance import InstanceGuard; "
            f"g=InstanceGuard(Path({str(domain)!r})); " + code
        )],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
    )


def test_duplicate_launch_is_blocked_and_queued_activation_is_delivered(tmp_path):
    owner = InstanceGuard(tmp_path)
    activated = threading.Event()
    window = SimpleNamespace(show=lambda: None, restore=activated.set)
    try:
        assert owner.acquire()
        process = child(tmp_path, "print(g.acquire()); g.close()")
        output, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
        assert output.strip() == "False"
        # Activation arrives even if the original GUI had not finished booting.
        owner.bind_window(window)
        assert activated.wait(5)
    finally:
        owner.close()


def test_restart_handoff_waits_for_old_owner(tmp_path):
    owner = InstanceGuard(tmp_path)
    process = None
    try:
        assert owner.acquire()
        process = child(tmp_path, "print('waiting'); print(g.acquire(wait_ms=5000)); g.close()")
        assert process.stdout.readline().strip() == "waiting"
        owner.close()
        output, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
        assert output.strip() == "True"
    finally:
        owner.close()
        if process and process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_os_releases_ownership_when_process_crashes(tmp_path):
    process = child(tmp_path, "print(g.acquire()); input()")
    try:
        assert process.stdout.readline().strip() == "True"
        process.kill()
        process.communicate(timeout=10)
        replacement = InstanceGuard(tmp_path)
        try:
            assert replacement.acquire()
        finally:
            replacement.close()
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)


def test_instance_domain_is_shared_by_stable_and_preview_installs(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("FINESUB_APP_ROOT", str(tmp_path / "Stable"))
    first = instance_domain()
    monkeypatch.setenv("FINESUB_APP_ROOT", str(tmp_path / "Preview"))
    assert instance_domain() == first == tmp_path / "FineSub" / "user-data"


def test_activation_handoff_targets_main_window_not_the_closed_startup(tmp_path):
    guard = InstanceGuard(tmp_path)
    old_activated, new_activated = threading.Event(), threading.Event()
    try:
        assert guard.acquire()
        guard.bind_window(SimpleNamespace(show=lambda: None, restore=old_activated.set))
        guard.bind_window(SimpleNamespace(show=lambda: None, restore=new_activated.set))
        # Windows mutex ownership is thread-specific, so use another process.
        process = child(tmp_path, "print(g.acquire()); g.close()")
        output, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
        assert output.strip() == "False"
        assert new_activated.wait(5)
        assert not old_activated.is_set()
    finally:
        guard.close()
