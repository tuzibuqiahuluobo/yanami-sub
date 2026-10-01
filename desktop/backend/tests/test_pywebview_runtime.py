from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from types import ModuleType
import pytest

from desktop.backend.launcher.main import choose_agent_file, choose_python_interpreter, install_frozen_pywebview_win32


def test_frozen_win32_source_is_registered_as_pywebview_platform(tmp_path) -> None:
    root = tmp_path / "win32-load"
    source = root / "win32.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("MARKER = 'loaded-from-source'\n", encoding="utf-8")

    webview = ModuleType("webview")
    webview.__path__ = []  # type: ignore[attr-defined]
    platforms = ModuleType("webview.platforms")
    platforms.__path__ = []  # type: ignore[attr-defined]
    previous = {
        name: sys.modules.get(name)
        for name in ("webview", "webview.platforms", "webview.platforms.win32")
    }
    sys.modules["webview"] = webview
    sys.modules["webview.platforms"] = platforms
    try:
        install_frozen_pywebview_win32(source)

        loaded = sys.modules["webview.platforms.win32"]
        assert loaded.MARKER == "loaded-from-source"  # type: ignore[attr-defined]
        assert platforms.win32 is loaded  # type: ignore[attr-defined]
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.parametrize("result", [
    (r"C:\Python312\python.exe",), [r"C:\Python312\python.exe"],
    r"C:\Python312\python.exe", None, (),
])
def test_python_picker_filters_reach_the_native_dialog_without_a_parser_error(result) -> None:
    import webview
    from webview.util import parse_file_type

    calls = []

    class Window:
        def create_file_dialog(self, dialog_type, *, file_types):
            # pywebview performs this validation before opening the OS dialog.
            parsed = [parse_file_type(value) for value in file_types]
            calls.append((dialog_type, parsed))
            return result

    selected = choose_python_interpreter(Window())
    assert calls[0][0] == webview.FileDialog.OPEN
    assert [mask for _label, mask in calls[0][1]] == ["*.exe", "*.*"]
    assert selected == (r"C:\Python312\python.exe" if result else None)


def test_python_picker_does_not_swallow_a_native_dialog_error() -> None:
    class Window:
        def create_file_dialog(self, *_args, **_kwargs):
            raise RuntimeError("Native file picker unavailable")

    with pytest.raises(RuntimeError, match="Native file picker"):
        choose_python_interpreter(Window())


@pytest.mark.parametrize("result", [
    (r"D:\Agent\codex.exe",), [r"D:\Agent\codex.exe"],
    r"D:\Agent\codex.exe", None, (),
])
def test_agent_picker_uses_valid_native_filters_and_handles_cancel(result) -> None:
    import webview
    from webview.util import parse_file_type

    calls = []

    class Window:
        def create_file_dialog(self, dialog_type, *, file_types):
            calls.append((dialog_type, [parse_file_type(value) for value in file_types]))
            return result

    assert choose_agent_file(Window()) == (r"D:\Agent\codex.exe" if result else None)
    assert calls[0][0] == webview.FileDialog.OPEN
    assert [mask for _label, mask in calls[0][1]] == ["*.exe;*.js", "*.*"]


def test_agent_picker_surfaces_native_dialog_errors() -> None:
    class Window:
        def create_file_dialog(self, *_args, **_kwargs):
            raise RuntimeError("Native file picker unavailable")

    with pytest.raises(RuntimeError, match="Native file picker"):
        choose_agent_file(Window())
