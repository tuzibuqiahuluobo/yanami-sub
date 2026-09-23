from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import desktop.backend.settings.local_agents as local_agents
from desktop.backend.settings.local_agents import (
    COMMANDS_ENV,
    configure_local_agents,
    discover_local_agent_commands,
    install_local_agent_command_overrides,
)


def test_discovery_supports_native_npm_and_dsh_source_installs(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    node = bin_dir / "node.exe"
    codex = bin_dir / "codex.exe"
    node.write_bytes(b"node")
    codex.write_bytes(b"codex")
    claude = (
        bin_dir
        / "node_modules"
        / "@anthropic-ai"
        / "claude-code"
        / "cli.js"
    )
    claude.parent.mkdir(parents=True)
    claude.write_text("", encoding="utf-8")
    dsh_root = tmp_path / "deepseek-harness"
    dsh = dsh_root / "apps" / "cli" / "lib" / "bin.js"
    dsh.parent.mkdir(parents=True)
    dsh.write_text("", encoding="utf-8")
    workbuddy_entry = tmp_path / "WorkBuddy" / "cli" / "codebuddy"
    workbuddy_entry.parent.mkdir(parents=True)
    workbuddy_entry.write_text("", encoding="utf-8")
    (bin_dir / "codebuddy").write_text(
        f'#!/bin/sh\n"ignored-node" "{workbuddy_entry}"\n',
        encoding="utf-8",
    )
    workbuddy_versions = (
        tmp_path / "home" / ".workbuddy" / "binaries" / "node" / "versions"
    )
    (workbuddy_versions / "22.22.2").mkdir(parents=True)
    workbuddy_node = workbuddy_versions / "22.22.2" / "node.exe"
    workbuddy_node.write_bytes(b"node")
    (workbuddy_versions / "current").write_text("22.22.2", encoding="utf-8")

    commands = discover_local_agent_commands(
        environ={
            "PATH": str(bin_dir),
            "USERPROFILE": str(tmp_path / "home"),
            "LOCALAPPDATA": str(tmp_path / "local"),
        },
        source_roots=[dsh_root],
    )

    assert commands["LOCAL_CODEX"] == (str(codex.resolve()),)
    assert commands["LOCAL_CLAUDE"] == (
        str(node.resolve()),
        str(claude.resolve()),
    )
    assert commands["LOCAL_DSH"] == (
        str(node.resolve()),
        str(dsh.resolve()),
    )
    assert commands["LOCAL_WORKBUDDY"] == (
        str(workbuddy_node.resolve()),
        str(workbuddy_entry.resolve()),
    )


def test_inaccessible_npm_candidate_does_not_hide_healthy_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = tmp_path / "broken"
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    node = healthy / "node.exe"
    node.write_bytes(b"node")
    claude = healthy / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    claude.parent.mkdir(parents=True)
    claude.write_text("", encoding="utf-8")
    inaccessible = broken / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
    original_is_file = Path.is_file

    def is_file(path: Path) -> bool:
        if path == inaccessible:
            raise OSError(448, "untrusted mount point")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", is_file)
    commands = discover_local_agent_commands(
        environ={
            "PATH": os.pathsep.join((str(broken), str(healthy))),
            "LOCALAPPDATA": str(tmp_path / "local"),
            "USERPROFILE": str(tmp_path / "home"),
        },
        source_roots=[],
    )

    assert commands["LOCAL_CLAUDE"] == (str(node.resolve()), str(claude.resolve()))


def test_optional_agent_scan_error_does_not_abort_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_discovery() -> dict[str, tuple[str, ...]]:
        raise OSError(448, "untrusted mount point")

    monkeypatch.setattr(local_agents, "discover_local_agent_commands", fail_discovery)
    monkeypatch.setattr(local_agents, "install_local_agent_command_overrides", lambda: {})
    monkeypatch.setenv(COMMANDS_ENV, "before")

    assert configure_local_agents() == {}
    assert json.loads(os.environ[COMMANDS_ENV]) == {}


def test_resolved_command_is_used_by_the_core_driver(
    monkeypatch,
) -> None:
    command = [r"C:\Program Files\nodejs\node.exe", r"G:\deepseek-harness\apps\cli\lib\bin.js"]
    monkeypatch.setenv(COMMANDS_ENV, json.dumps({"LOCAL_DSH": command}))

    install_local_agent_command_overrides()

    from finesub.llm.routing.execution_policy import ExecutionSettings

    config = ExecutionSettings().driver_config_for(
        provider_tier="LOCAL_DSH",
        model="deepseek-chat",
    )
    assert config.command == tuple(command)
