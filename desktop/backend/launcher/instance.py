"""Windows GUI ownership, independent of the selected app snapshot/version.

Copies of Yanami Sub share personal settings, so ownership is per user-data
domain and Windows session, not per exe or RC version. The OS releases the
mutex after a crash. No PID files, process killing, or credential access.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import threading

RESTART_WAIT_ENV = "YANAMI_SUB_RESTART_WAIT"


def instance_domain() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "FineSub" / "user-data"


class InstanceGuard:
    def __init__(self, domain: Path):
        self._owned = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._window = None
        self._kernel = None
        self._mutex = self._event = None
        if os.name != "nt":
            return  # The shipped desktop launcher is Windows-only.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("CreateMutexW", [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            ("CreateEventW", [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            ("WaitForSingleObject", [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            ("SetEvent", [wintypes.HANDLE], wintypes.BOOL),
            ("ReleaseMutex", [wintypes.HANDLE], wintypes.BOOL),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            method = getattr(kernel, name)
            method.argtypes, method.restype = args, result
        identity = os.path.normcase(str(domain.resolve())).encode("utf-8")
        prefix = "Local\\YanamiSub-" + hashlib.sha256(identity).hexdigest()
        self._kernel = kernel
        self._mutex = kernel.CreateMutexW(None, False, prefix + "-owner")
        self._event = kernel.CreateEventW(None, False, False, prefix + "-activate")
        if not self._mutex or not self._event:
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def acquire(self, *, wait_ms: int = 0) -> bool:
        if self._kernel is None:
            self._owned = True
            return True
        result = self._kernel.WaitForSingleObject(self._mutex, wait_ms)
        if result in (0, 0x80):  # WAIT_OBJECT_0 / WAIT_ABANDONED
            self._owned = True
            return True
        if result == 0x102:  # WAIT_TIMEOUT
            self._kernel.SetEvent(self._event)
            return False
        raise ctypes.WinError(ctypes.get_last_error())

    def bind_window(self, window) -> None:
        self._window = window
        if self._kernel is None or self._thread is not None:
            return

        def listen():
            while not self._stop.is_set():
                if self._kernel.WaitForSingleObject(self._event, 500) != 0:
                    continue
                try:
                    window = self._window
                    shown = getattr(getattr(window, "events", None), "shown", None)
                    if shown is not None:
                        shown.wait(10)
                    if not self._stop.is_set():
                        window.show()
                        window.restore()
                except Exception:
                    # A duplicate launch during shutdown must not crash the owner.
                    pass

        self._thread = threading.Thread(target=listen, name="yanami-activate", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=11)
            self._thread = None
        if self._kernel:
            if self._owned:
                self._kernel.ReleaseMutex(self._mutex)
            for handle in (self._event, self._mutex):
                if handle:
                    self._kernel.CloseHandle(handle)
        self._owned = False
        self._mutex = self._event = None


def acquire_instance() -> InstanceGuard | None:
    restarting = os.environ.pop(RESTART_WAIT_ENV, "") == "1"
    guard = InstanceGuard(instance_domain())
    try:
        if guard.acquire(wait_ms=60_000 if restarting else 0):
            return guard
        if restarting:
            raise RuntimeError("上一个 Yanami Sub 尚未退出，重启等待超时；请稍后再打开。 / Restart timed out.")
        return None
    finally:
        if not guard._owned:
            guard.close()
