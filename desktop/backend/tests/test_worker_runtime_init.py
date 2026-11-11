import ast
import builtins
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from desktop.backend.worker.runtime import initialize_native_paths


def test_initializer_uses_core_and_reports_failure_without_crashing(monkeypatch, capsys):
    seen = []
    def initialize():
        seen.append(True)
        return "native UTF-8 unavailable"
    monkeypatch.setitem(sys.modules, "finesub.speech.runtime.native_paths", SimpleNamespace(use_utf8_crt_locale=initialize))
    initialize_native_paths()
    assert seen == [True]
    assert "Warning: native UTF-8 unavailable" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["finesub.speech.runtime.native_paths", "some_required_dependency"])
def test_only_a_missing_legacy_initializer_is_optional(monkeypatch, missing):
    original = builtins.__import__
    def import_module(name, *args, **kwargs):
        if name == "finesub.speech.runtime.native_paths":
            raise ModuleNotFoundError("missing", name=missing)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", import_module)
    if missing == "finesub.speech.runtime.native_paths":
        initialize_native_paths()
    else:
        with pytest.raises(ModuleNotFoundError, match="missing"):
            initialize_native_paths()


@pytest.mark.parametrize("module", ["main", "batch_main", "knowledge_main", "prefetch"])
def test_each_isolated_worker_initializes_paths_before_dispatch(module):
    path = Path(__file__).parents[1] / "worker" / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    calls = {node.func.id: node.lineno for node in ast.walk(main) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    dispatch = {"main": "run_request", "batch_main": "run_batch_request", "knowledge_main": "_dispatch", "prefetch": "_run_prefetch"}[module]
    assert calls["initialize_native_paths"] < calls[dispatch]
    if module in {"main", "batch_main"}:
        assert calls["initialize_native_paths"] < calls["configure_compiler_output"] < calls[dispatch]
        assert calls["configure_compiler_output"] < calls["configure_qwen_attention"] < calls[dispatch]


def test_single_and_batch_share_style_retaining_cleanup():
    from desktop.backend.worker import batch_main, main

    assert batch_main.cleanup_task_intermediates is main.cleanup_task_intermediates
