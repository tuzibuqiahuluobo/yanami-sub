"""Desktop discovery and command overrides for FineSub local-agent CLIs.

FineSub deliberately resolves native commands without a shell. That is the
right execution policy, but a Windows desktop process often inherits an old
PATH and some supported tools are installed as Node entry scripts or source
checkouts rather than native executables. This module finds those concrete
interpreter/script pairs without running them, then feeds the same command to
both the readiness probe and isolated task workers.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
import ctypes
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import shutil
import threading


COMMANDS_ENV = "YANAMI_SUB_LOCAL_AGENT_COMMANDS"
_PATCH_MARKER = "_yanami_sub_command_overrides"
_ERROR_MODE_LOCK = threading.Lock()


def _split_path(value: str) -> Iterator[Path]:
    for raw in value.split(os.pathsep):
        item = raw.strip().strip('"')
        if item:
            yield Path(os.path.expandvars(item)).expanduser()


def refresh_windows_path(environ: dict[str, str] | None = None) -> str:
    """Merge fresh user/machine PATH values into this long-running process."""

    target = environ if environ is not None else os.environ
    if os.name != "nt":
        return target.get("PATH", "")
    values = [target.get("PATH", "")]
    try:
        import winreg

        locations = (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        )
        for hive, subkey in locations:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "Path")
                if isinstance(value, str):
                    values.append(os.path.expandvars(value))
            except OSError:
                continue
    except ImportError:  # pragma: no cover - Windows-only module
        pass

    seen: set[str] = set()
    merged: list[str] = []
    for value in values:
        for path in _split_path(value):
            normalized = os.path.normcase(os.path.abspath(path))
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(str(path))
    target["PATH"] = os.pathsep.join(merged)
    return target["PATH"]


def _native_command(
    name: str, environ: Mapping[str, str] | None = None
) -> Path | None:
    search_path = None if environ is None else environ.get("PATH", "")
    for spelling in (f"{name}.exe", name):
        found = shutil.which(spelling, path=search_path)
        if found and Path(found).suffix.lower() == ".exe":
            return Path(found).resolve()
    return None


def _newest(paths: Iterable[Path]) -> Path | None:
    candidates: list[tuple[float, Path]] = []
    for path in paths:
        try:
            if path.is_file():
                candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1].resolve()


def _node(environ: Mapping[str, str]) -> Path | None:
    return _native_command("node", environ)


def _path_directories(environ: Mapping[str, str]) -> list[Path]:
    return list(_split_path(environ.get("PATH", "")))


def _npm_entry(
    path_directories: Iterable[Path],
    package: tuple[str, ...],
    relative: tuple[str, ...],
) -> Path | None:
    for directory in path_directories:
        candidate = directory.joinpath("node_modules", *package, *relative)
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _npm_codex(path_directories: Iterable[Path]) -> Path | None:
    candidates: list[Path] = []
    for directory in path_directories:
        package_root = (
            directory
            / "node_modules"
            / "@openai"
            / "codex"
            / "node_modules"
            / "@openai"
        )
        candidates.extend(package_root.glob("codex-win32-*/vendor/*/bin/codex.exe"))
        candidates.extend(package_root.glob("codex-win32-*/vendor/*/codex/codex.exe"))
    return _newest(candidates)


def _workbuddy_command(
    environ: Mapping[str, str],
    path_directories: Iterable[Path],
    fallback_node: Path | None,
) -> tuple[str, ...] | None:
    entry: Path | None = None
    for directory in path_directories:
        shim = directory / "codebuddy"
        if not shim.is_file():
            continue
        try:
            text = shim.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for quoted in re.findall(r'"([^"]+)"', text):
            candidate = Path(quoted)
            if candidate.name.lower().startswith("codebuddy") and candidate.is_file():
                entry = candidate.resolve()
                break
        if entry is not None:
            break
    if entry is None:
        local_app_data = environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidate = (
                Path(local_app_data)
                / "Programs"
                / "WorkBuddy"
                / "resources"
                / "app.asar.unpacked"
                / "cli"
                / "bin"
                / "codebuddy"
            )
            if candidate.is_file():
                entry = candidate.resolve()
    if entry is None:
        return None

    home = Path(environ.get("USERPROFILE") or Path.home())
    versions = home / ".workbuddy" / "binaries" / "node" / "versions"
    try:
        current = (versions / "current").read_text(encoding="utf-8").strip()
    except OSError:
        current = ""
    bundled_node = versions / current / "node.exe" if current else None
    node = (
        bundled_node.resolve()
        if bundled_node is not None and bundled_node.is_file()
        else fallback_node
    )
    return (str(node), str(entry)) if node is not None else None


def _windows_drive_roots() -> list[Path]:
    if os.name != "nt":
        return []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    return [
        Path(f"{chr(ord('A') + index)}:\\")
        for index in range(26)
        if bitmask & (1 << index)
    ]


def _source_roots(environ: Mapping[str, str]) -> list[Path]:
    """Safe source checkout discovery limited to user directories.

    RC6.13+: Removed drive-root scanning (X:\deepseek-harness) to prevent
    security issue where arbitrary bin.js at drive roots could be executed.
    Only checks user-controlled directories now.
    """
    home = Path(environ.get("USERPROFILE") or Path.home())
    roots: list[Path] = []
    for parent in (home, home / "Documents", home / "source" / "repos"):
        roots.append(parent / "deepseek-harness")
    # RC6.13+: Removed _windows_drive_roots() scan for security.
    # Drive roots (C:\, D:\, etc.) are writable by other users and network
    # shares, allowing code execution via planted bin.js files.
    # Users with non-standard install locations should use Settings to
    # specify the path explicitly.
    return roots


def discover_local_agent_commands(
    *,
    environ: dict[str, str] | None = None,
    source_roots: Iterable[Path] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Resolve supported agents to shell-free commands without launching any."""

    target = environ if environ is not None else os.environ
    refresh_windows_path(target)
    path_directories = _path_directories(target)
    node = _node(target)
    commands: dict[str, tuple[str, ...]] = {}

    local_app_data_value = target.get("LOCALAPPDATA", "").strip()
    local_app_data = Path(local_app_data_value) if local_app_data_value else None
    codex = _native_command("codex", target)
    if codex is None and local_app_data is not None:
        codex = _newest(
            (local_app_data / "OpenAI" / "Codex" / "bin").glob("*/codex.exe")
        )
    if codex is None:
        codex = _npm_codex(path_directories)
    if codex is not None:
        commands["LOCAL_CODEX"] = (str(codex),)

    claude = _native_command("claude", target)
    if claude is not None:
        commands["LOCAL_CLAUDE"] = (str(claude),)
    elif node is not None:
        claude_entry = _npm_entry(
            path_directories,
            ("@anthropic-ai", "claude-code"),
            ("cli.js",),
        )
        if claude_entry is not None:
            commands["LOCAL_CLAUDE"] = (str(node), str(claude_entry))

    dsh = _native_command("dsh", target)
    if dsh is not None:
        commands["LOCAL_DSH"] = (str(dsh),)
    elif node is not None:
        dsh_entry = _npm_entry(
            path_directories,
            ("@deepseek-ai", "dsh"),
            ("lib", "bin.js"),
        )
        if dsh_entry is None:
            for root in source_roots or _source_roots(target):
                candidate = root / "apps" / "cli" / "lib" / "bin.js"
                if candidate.is_file():
                    dsh_entry = candidate.resolve()
                    break
        if dsh_entry is not None:
            commands["LOCAL_DSH"] = (str(node), str(dsh_entry))

    agy = _native_command("agy", target)
    if agy is not None:
        commands["LOCAL_AGY"] = (str(agy),)

    workbuddy = _native_command("codebuddy", target)
    if workbuddy is not None:
        commands["LOCAL_WORKBUDDY"] = (str(workbuddy),)
    else:
        workbuddy_command = _workbuddy_command(target, path_directories, node)
        if workbuddy_command is not None:
            commands["LOCAL_WORKBUDDY"] = workbuddy_command
    return commands


def _commands_from_environment() -> dict[str, tuple[str, ...]]:
    try:
        document = json.loads(os.environ.get(COMMANDS_ENV, "{}"))
    except (TypeError, ValueError):
        return {}
    if not isinstance(document, dict):
        return {}
    commands: dict[str, tuple[str, ...]] = {}
    for tier, raw in document.items():
        if not isinstance(tier, str) or not isinstance(raw, list):
            continue
        command = tuple(str(part) for part in raw if isinstance(part, str) and part)
        if command:
            commands[tier.strip().upper()] = command
    return commands


def install_local_agent_command_overrides() -> dict[str, tuple[str, ...]]:
    """Install one process-local adapter over FineSub's driver config seam."""

    from finesub.llm.routing import execution_policy

    commands = _commands_from_environment()
    if getattr(execution_policy.ExecutionSettings, _PATCH_MARKER, False):
        return commands
    original = execution_policy.ExecutionSettings.driver_config_for

    def driver_config_for(self, *, provider_tier: str, model: str):
        config = original(self, provider_tier=provider_tier, model=model)
        command = _commands_from_environment().get(provider_tier.strip().upper())
        return replace(config, command=command) if command else config

    execution_policy.ExecutionSettings.driver_config_for = driver_config_for
    setattr(execution_policy.ExecutionSettings, _PATCH_MARKER, True)
    return commands


def configure_local_agents() -> dict[str, tuple[str, ...]]:
    try:
        commands = discover_local_agent_commands()
    except OSError:
        # Optional Agent discovery must not prevent the desktop from opening.
        commands = {}
    os.environ[COMMANDS_ENV] = json.dumps(commands, ensure_ascii=False)
    install_local_agent_command_overrides()
    return commands


@contextmanager
def suppress_windows_child_error_dialogs():
    """Keep a broken optional CLI from opening a modal system error box."""

    if os.name != "nt":
        yield
        return
    # These are inherited by child processes. The probe still receives the
    # actual non-zero exit/error and reports it in the readiness row.
    flags = 0x0001 | 0x0002 | 0x8000  # FAILCRITICAL | NOGPFAULT | NOOPENFILE
    with _ERROR_MODE_LOCK:
        kernel32 = ctypes.windll.kernel32
        previous = kernel32.SetErrorMode(flags)
        try:
            yield
        finally:
            kernel32.SetErrorMode(previous)
