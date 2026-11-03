"""Pinned Torch/MSVC diagnostic decoding; model/file encodings stay UTF-8."""
from __future__ import annotations

import codecs
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
import sys

_WINDOWS = sys.platform == "win32"
_ANSI_ENCODING = "mbcs"
_CODEC = "yanami_compiler_output"


def _decode_output(data, errors="strict"):
    raw = bytes(data)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode(_ANSI_ENCODING, errors=errors)
    return text, len(raw)


def _lookup_codec(name):
    if name == _CODEC:
        return codecs.CodecInfo(name=_CODEC, encode=None, decode=_decode_output)
    return None


codecs.register(_lookup_codec)


def configure_compiler_output() -> None:
    if not _WINDOWS:
        return
    try:
        torch_version = version("torch").split("+", 1)[0]
    except PackageNotFoundError:
        return  # LLM-only/lightweight workers need not have the speech stack.
    if torch_version != "2.11.0":
        return
    try:
        # shortcut: private Torch 2.11 decoder; revalidate when changing the runtime pin.
        builder = import_module("torch._inductor.cpp_builder")
        if builder.SUBPROCESS_DECODE_ARGS == (_CODEC, "replace"):
            return
        if not (isinstance(builder.SUBPROCESS_DECODE_ARGS, tuple)
                and len(builder.SUBPROCESS_DECODE_ARGS) == 1):
            raise RuntimeError("unexpected Torch compiler decode contract")
        # Torch 2.11 inherits UTF-8 LC_CTYPE, while localized cl.exe emits ANSI.
        builder.SUBPROCESS_DECODE_ARGS = (_CODEC, "replace")
    except Exception as error:
        print(
            f"Warning: compiler output compatibility unavailable ({type(error).__name__}); "
            "optional GPU compilation may fall back.",
            file=sys.stderr,
        )
