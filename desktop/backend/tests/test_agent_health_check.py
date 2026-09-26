"""Tests for agent health check module."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

import pytest

from desktop.backend.worker.agent_health_check import (
    AgentHealthReport,
    AgentStatus,
    check_agent_health,
    check_api_keys_available,
    validate_source_availability,
    _check_agent_tier,
    _executable_exists,
)
from desktop.backend.settings.local_agents import COMMANDS_ENV


def test_agent_status_to_dict():
    """Test AgentStatus serialization."""
    status = AgentStatus(
        tier="LOCAL_DSH",
        available=True,
        reason="ok",
        detail="All good",
    )
    assert status.to_dict() == {
        "tier": "LOCAL_DSH",
        "available": True,
        "reason": "ok",
        "detail": "All good",
    }


def test_health_report_available_tiers():
    """Test filtering available tiers from health report."""
    report = AgentHealthReport(
        statuses=(
            AgentStatus("LOCAL_DSH", True),
            AgentStatus("LOCAL_AGY", False, "quota"),
            AgentStatus("LOCAL_CLAUDE", True),
        ),
        any_available=True,
        source="agent",
    )
    assert report.available_tiers() == ["LOCAL_DSH", "LOCAL_CLAUDE"]
    assert report.unavailable_tiers() == ["LOCAL_AGY"]


def test_health_report_get_status():
    """Test retrieving specific tier status."""
    report = AgentHealthReport(
        statuses=(
            AgentStatus("LOCAL_DSH", True),
            AgentStatus("LOCAL_AGY", False, "quota"),
        ),
        any_available=True,
        source="agent",
    )
    assert report.get_status("LOCAL_DSH").available is True
    assert report.get_status("LOCAL_AGY").available is False
    assert report.get_status("NONEXISTENT") is None


def test_health_report_format_summary():
    """Test summary formatting."""
    report = AgentHealthReport(
        statuses=(
            AgentStatus("LOCAL_DSH", True),
            AgentStatus("LOCAL_AGY", False, "quota"),
        ),
        any_available=True,
        source="agent",
    )
    summary = report.format_summary()
    assert "LOCAL_DSH" in summary
    assert "LOCAL_AGY" in summary
    assert "可用" in summary
    assert "不可用" in summary


def test_executable_exists_absolute_path(tmp_path):
    """Test executable check with absolute path."""
    # Create a dummy executable
    exe = tmp_path / "dummy.exe"
    exe.write_text("dummy")
    exe.chmod(0o755)

    assert _executable_exists(str(exe)) is True
    assert _executable_exists(str(tmp_path / "nonexistent.exe")) is False


@patch.dict(os.environ, {}, clear=True)
def test_check_agent_tier_not_configured():
    """Test checking an unconfigured agent tier."""
    status = _check_agent_tier("LOCAL_DSH", "")
    assert status.available is False
    assert status.reason == "command_not_configured"


@patch("subprocess.run")
def test_check_agent_tier_version_success(mock_run):
    """Test successful version check."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="version 1.0.0",
        stderr="",
    )

    with patch("desktop.backend.worker.agent_health_check._executable_exists", return_value=True):
        status = _check_agent_tier("LOCAL_DSH", ["dsh", "--version"])

    assert status.available is True
    assert status.tier == "LOCAL_DSH"


@patch("subprocess.run")
def test_check_agent_tier_quota_error(mock_run):
    """Test detecting quota errors."""
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="Error: Insufficient Balance",
    )

    with patch("desktop.backend.worker.agent_health_check._executable_exists", return_value=True):
        status = _check_agent_tier("LOCAL_DSH", ["dsh"])

    assert status.available is False
    assert status.reason == "quota"
    assert "余额不足" in status.detail or "配额不足" in status.detail


@patch("subprocess.run")
def test_check_agent_tier_provider_disabled(mock_run):
    """Test detecting provider disabled errors."""
    mock_run.return_value = MagicMock(
        returncode=1,
        stdout="",
        stderr="Error: provider disabled",
    )

    with patch("desktop.backend.worker.agent_health_check._executable_exists", return_value=True):
        status = _check_agent_tier("LOCAL_DSH", ["dsh"])

    assert status.available is False
    assert status.reason == "provider_disabled"


@patch("subprocess.run")
def test_check_agent_tier_timeout(mock_run):
    """Test handling timeout."""
    mock_run.side_effect = subprocess.TimeoutExpired("dsh", 10)

    with patch("desktop.backend.worker.agent_health_check._executable_exists", return_value=True):
        status = _check_agent_tier("LOCAL_DSH", ["dsh"])

    assert status.available is False
    assert status.reason == "timeout"


@patch.dict(os.environ, {COMMANDS_ENV: json.dumps({
    "LOCAL_DSH": ["dsh"],
    "LOCAL_AGY": ["agy"],
})}, clear=True)
@patch("desktop.backend.worker.agent_health_check._check_agent_tier")
def test_check_agent_health(mock_check_tier):
    """Test full agent health check."""
    mock_check_tier.side_effect = [
        AgentStatus("LOCAL_AGY", True),
        AgentStatus("LOCAL_DSH", False, "quota"),
    ]

    report = check_agent_health()

    assert len(report.statuses) == 2
    assert report.any_available is True
    assert report.source == "agent"


@patch.dict(os.environ, {}, clear=True)
def test_check_agent_health_no_config():
    """Test health check with no configured agents."""
    report = check_agent_health()

    assert len(report.statuses) == 0
    assert report.any_available is False


@patch.dict(os.environ, {"GEMINI_FREE": "test_key"}, clear=True)
def test_check_api_keys_available():
    """Test API key availability check."""
    assert check_api_keys_available() is True


@patch.dict(os.environ, {}, clear=True)
def test_check_api_keys_not_available():
    """Test API key check when none configured."""
    assert check_api_keys_available() is False


@patch.dict(os.environ, {"GEMINI_FREE": "test_key"}, clear=True)
def test_validate_source_api_with_key():
    """Test validating API source with key configured."""
    available, error = validate_source_availability("api", check_agents=False)
    assert available is True
    assert error == ""


@patch.dict(os.environ, {}, clear=True)
def test_validate_source_api_without_key():
    """Test validating API source without key."""
    available, error = validate_source_availability("api", check_agents=False)
    assert available is False
    assert "API 密钥" in error


@patch.dict(os.environ, {COMMANDS_ENV: json.dumps({"LOCAL_DSH": ["dsh"]})}, clear=True)
def test_validate_source_agent_quick_check():
    """Test quick agent validation without full health check."""
    available, error = validate_source_availability("agent", check_agents=False)
    assert available is True
    assert error == ""


@patch.dict(os.environ, {}, clear=True)
def test_validate_source_agent_no_config():
    """Test agent validation with no agents configured."""
    available, error = validate_source_availability("agent", check_agents=False)
    assert available is False
    assert "Agent" in error


@patch("desktop.backend.worker.agent_health_check.check_agent_health")
def test_validate_source_agent_full_check(mock_health):
    """Test agent validation with full health check."""
    mock_health.return_value = AgentHealthReport(
        statuses=(AgentStatus("LOCAL_DSH", True),),
        any_available=True,
        source="agent",
    )

    available, error = validate_source_availability("agent", check_agents=True)
    assert available is True
    assert error == ""
    mock_health.assert_called_once()


@patch("desktop.backend.worker.agent_health_check.check_agent_health")
def test_validate_source_agent_all_unavailable(mock_health):
    """Test agent validation when all agents unavailable."""
    mock_health.return_value = AgentHealthReport(
        statuses=(AgentStatus("LOCAL_DSH", False, "quota", "余额不足"),),
        any_available=False,
        source="agent",
    )

    available, error = validate_source_availability("agent", check_agents=True)
    assert available is False
    assert "不可用" in error
    mock_health.assert_called_once()
