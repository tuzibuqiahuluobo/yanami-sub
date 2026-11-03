import locale
from types import SimpleNamespace

import pytest

from desktop.backend.worker import compiler_output


@pytest.mark.parametrize("text,encoding", [
    ("Microsoft compiler", "ascii"),
    ("编译完成：中文_日本語", "utf-8"),
    ("用于 x64 的 Microsoft 编译器", "cp936"),
])
def test_compiler_codec_accepts_utf8_and_windows_ansi(monkeypatch, text, encoding):
    monkeypatch.setattr(compiler_output, "_ANSI_ENCODING", "cp936")
    raw = text.encode(encoding)
    assert raw.decode(compiler_output._CODEC, errors="replace") == text
    assert compiler_output._decode_output(memoryview(raw))[1] == len(raw)


def test_compiler_codec_preserves_utf8_on_a_non_utf8_windows_locale(monkeypatch):
    monkeypatch.setattr(compiler_output, "_ANSI_ENCODING", "cp1252")
    assert "中文".encode("utf-8").decode(compiler_output._CODEC, errors="replace") == "中文"
    assert b"r\xe9sum\xe9".decode(compiler_output._CODEC, errors="replace") == "résumé"
    assert b"\x81".decode(compiler_output._CODEC, errors="replace") == "\ufffd"


@pytest.mark.parametrize("torch_version,windows,changed", [
    ("2.11.0+cu128", True, True), ("2.12.0", True, False), ("2.11.0", False, False),
])
def test_only_the_pinned_windows_torch_decode_boundary_is_changed(monkeypatch, torch_version, windows, changed):
    monkeypatch.setattr(compiler_output, "_WINDOWS", windows)
    monkeypatch.setattr(compiler_output, "version", lambda name: torch_version)
    builder = SimpleNamespace(SUBPROCESS_DECODE_ARGS=("utf-8",))
    imports = []
    def load(name):
        imports.append(name)
        return builder
    monkeypatch.setattr(compiler_output, "import_module", load)
    original_locale = locale.setlocale(locale.LC_CTYPE)
    compiler_output.configure_compiler_output()
    assert bool(imports) is changed
    assert builder.SUBPROCESS_DECODE_ARGS == ((compiler_output._CODEC, "replace") if changed else ("utf-8",))
    assert locale.setlocale(locale.LC_CTYPE) == original_locale
    compiler_output.configure_compiler_output()  # Idempotent within a batch worker.


def test_missing_torch_does_not_import_or_warn(monkeypatch, capsys):
    monkeypatch.setattr(compiler_output, "_WINDOWS", True)
    def absent(name):
        raise compiler_output.PackageNotFoundError(name)
    monkeypatch.setattr(compiler_output, "version", absent)
    monkeypatch.setattr(compiler_output, "import_module", lambda name: pytest.fail("must not import Torch"))
    compiler_output.configure_compiler_output()
    assert not capsys.readouterr().err


def test_changed_private_contract_is_reported_and_left_alone(monkeypatch, capsys):
    monkeypatch.setattr(compiler_output, "_WINDOWS", True)
    monkeypatch.setattr(compiler_output, "version", lambda name: "2.11.0")
    builder = SimpleNamespace(SUBPROCESS_DECODE_ARGS=("utf-8", "strict"))
    monkeypatch.setattr(compiler_output, "import_module", lambda name: builder)
    compiler_output.configure_compiler_output()
    assert builder.SUBPROCESS_DECODE_ARGS == ("utf-8", "strict")
    assert "Warning:" in capsys.readouterr().err
