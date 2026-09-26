"""Agent availability pre-check to fail fast with clear user guidance.

Validates local agent availability before starting expensive ASR stages.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Literal

from desktop.backend.settings.local_agents import COMMANDS_ENV

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentStatus:
    """Health status for one local agent tier."""

    tier: str
    available: bool
    reason: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "available": self.available,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class AgentHealthReport:
    """Aggregated health check result for all configured agents."""

    statuses: tuple[AgentStatus, ...]
    any_available: bool
    source: Literal["agent", "api"]

    def available_tiers(self) -> list[str]:
        return [s.tier for s in self.statuses if s.available]

    def unavailable_tiers(self) -> list[str]:
        return [s.tier for s in self.statuses if not s.available]

    def get_status(self, tier: str) -> AgentStatus | None:
        return next((s for s in self.statuses if s.tier == tier), None)

    def format_summary(self) -> str:
        """Human-readable summary for logging."""
        if not self.statuses:
            return "未配置任何本地 Agent"

        available = self.available_tiers()
        unavailable = self.unavailable_tiers()

        parts = []
        if available:
            parts.append(f"可用：{', '.join(available)}")
        if unavailable:
            parts.append(f"不可用：{', '.join(unavailable)}")

        return "；".join(parts)

    def format_detailed_report(self) -> str:
        """Detailed report with reasons for failures."""
        if not self.statuses:
            return "未配置任何本地 Agent。请在设置中配置 Agent 或使用 API 模式。"

        lines = ["本地 Agent 健康检查："]
        for status in self.statuses:
            state = "✓ 可用" if status.available else "✗ 不可用"
            line = f"  {status.tier}: {state}"
            if status.reason:
                line += f" ({status.reason})"
            if status.detail:
                line += f"\n    详情：{status.detail}"
            lines.append(line)

        return "\n".join(lines)


def _check_agent_tier(tier: str, command: str | list) -> AgentStatus:
    """Check if one agent tier is actually usable.

    Runs a lightweight health check command to verify:
    - The CLI executable exists and is runnable
    - The CLI can respond to basic commands
    - No obvious configuration issues (missing auth, disabled provider, etc.)
    """

    if not command:
        return AgentStatus(
            tier=tier,
            available=False,
            reason="command_not_configured",
            detail="命令未配置",
        )

    # Parse command string to list
    if isinstance(command, str):
        import shlex
        try:
            cmd_parts = shlex.split(command)
        except ValueError as e:
            return AgentStatus(
                tier=tier,
                available=False,
                reason="invalid_command",
                detail=f"命令格式无效：{e}",
            )
    else:
        cmd_parts = list(command)

    if not cmd_parts:
        return AgentStatus(
            tier=tier,
            available=False,
            reason="empty_command",
            detail="命令为空",
        )

    # Check if the executable exists
    executable = cmd_parts[0]
    if not _executable_exists(executable):
        return AgentStatus(
            tier=tier,
            available=False,
            reason="executable_not_found",
            detail=f"找不到可执行文件：{executable}",
        )

    # Try a lightweight health check command
    # Most agent CLIs support --version or similar
    try:
        # Try --version first (most common)
        result = subprocess.run(
            [*cmd_parts, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode == 0:
            return AgentStatus(tier=tier, available=True)

        # Some CLIs might not support --version but still be functional
        # Check stderr for common error patterns
        stderr = result.stderr.lower()
        stdout = result.stdout.lower()
        combined = stderr + stdout

        # Check for auth/quota issues
        if any(marker in combined for marker in [
            "insufficient balance",
            "quota exceeded",
            "quota",
            "余额不足",
            "配额",
        ]):
            return AgentStatus(
                tier=tier,
                available=False,
                reason="quota",
                detail="配额不足或余额不足",
            )

        if any(marker in combined for marker in [
            "unauthorized",
            "authentication",
            "api key",
            "未授权",
            "认证",
        ]):
            return AgentStatus(
                tier=tier,
                available=False,
                reason="auth_failed",
                detail="认证失败，请检查 API 密钥",
            )

        if any(marker in combined for marker in [
            "provider disabled",
            "backend unavailable",
            "提供商被禁用",
        ]):
            return AgentStatus(
                tier=tier,
                available=False,
                reason="provider_disabled",
                detail="提供商被禁用",
            )

        # Version check failed but no obvious error - might still work
        # Return available with a warning
        logger.warning(
            "Agent %s --version returned non-zero but no obvious error; "
            "treating as available", tier
        )
        return AgentStatus(
            tier=tier,
            available=True,
            reason="version_check_failed",
            detail="版本检查失败但可能仍可用",
        )

    except subprocess.TimeoutExpired:
        return AgentStatus(
            tier=tier,
            available=False,
            reason="timeout",
            detail="健康检查超时（10秒）",
        )
    except Exception as e:
        return AgentStatus(
            tier=tier,
            available=False,
            reason="check_failed",
            detail=f"健康检查失败：{type(e).__name__}: {e}",
        )


def _executable_exists(executable: str) -> bool:
    """Check if an executable is available in PATH or as an absolute path."""

    # If it's an absolute path, check directly
    if os.path.isabs(executable):
        return os.path.isfile(executable) and os.access(executable, os.X_OK)

    # Otherwise check in PATH
    path_env = os.environ.get("PATH", "")
    if sys.platform == "win32":
        # Windows: check with common extensions
        extensions = os.environ.get("PATHEXT", ".exe;.bat;.cmd").split(";")
        for directory in path_env.split(os.pathsep):
            for ext in [""] + extensions:
                full_path = os.path.join(directory, executable + ext)
                if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                    return True
    else:
        # Unix-like: direct check
        for directory in path_env.split(os.pathsep):
            full_path = os.path.join(directory, executable)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                return True

    return False


def check_agent_health() -> AgentHealthReport:
    """Check health of all configured local agents.

    Returns an AgentHealthReport with status for each configured tier.
    This is a relatively lightweight check (< 10s total) that can be run
    before starting expensive ASR stages.
    """

    try:
        commands = json.loads(os.environ.get(COMMANDS_ENV, "{}"))
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        logger.warning("Failed to parse agent commands from env: %s", e)
        return AgentHealthReport(statuses=(), any_available=False, source="agent")

    if not isinstance(commands, dict):
        return AgentHealthReport(statuses=(), any_available=False, source="agent")

    statuses = []
    for tier in sorted(commands.keys()):
        command = commands[tier]
        if not command:
            continue
        status = _check_agent_tier(tier, command)
        statuses.append(status)
        logger.debug("Agent health check: %s -> %s", tier, status.to_dict())

    any_available = any(s.available for s in statuses)

    return AgentHealthReport(
        statuses=tuple(statuses),
        any_available=any_available,
        source="agent",
    )


def check_api_keys_available() -> bool:
    """Quick check if any API keys are configured."""

    # Check for common Gemini API key environment variables
    api_keys = [
        "GEMINI_FREE",
        "GEMINI_PAID",
        "GEMINI_API_KEY",
    ]

    return any(os.environ.get(key, "").strip() for key in api_keys)


def validate_source_availability(
    source: Literal["agent", "api", "auto"],
    *,
    check_agents: bool = True,
) -> tuple[bool, str]:
    """Validate that the requested model source is actually available.

    Args:
        source: The requested model source ("agent", "api", or "auto")
        check_agents: If True, perform full agent health checks (may take ~10s).
                     If False, only check if agents are configured.

    Returns:
        (is_available, error_message) tuple. error_message is empty if available.
    """

    if source == "manual":
        return True, ""

    if source == "api" or (source == "auto" and check_api_keys_available()):
        # API mode - check for keys
        if not check_api_keys_available():
            return False, (
                "未配置 Gemini API 密钥。请在设置中配置 API 密钥，"
                "或选择使用本地 Agent，或改用自动模式。"
            )
        return True, ""

    # Agent mode (or auto without API keys)
    if not check_agents:
        # Quick check: just verify agents are configured
        try:
            commands = json.loads(os.environ.get(COMMANDS_ENV, "{}"))
            has_agents = isinstance(commands, dict) and any(
                cmd for cmd in commands.values() if cmd
            )
            if not has_agents:
                return False, (
                    "未配置任何本地 Agent。请在设置中配置 Agent，"
                    "或选择使用 API 模式。"
                )
            return True, ""
        except (TypeError, ValueError, json.JSONDecodeError):
            return False, "Agent 配置格式错误"

    # Full agent health check
    report = check_agent_health()

    if not report.statuses:
        return False, (
            "未配置任何本地 Agent。请在设置中配置 Agent，"
            "或选择使用 API 模式。"
        )

    if not report.any_available:
        # All agents unavailable - provide detailed report
        detail = report.format_detailed_report()
        return False, (
            f"所有本地 Agent 均不可用。\n\n{detail}\n\n"
            f"请修复以上问题，或选择使用 API 模式。"
        )

    # At least some agents are available
    unavailable = report.unavailable_tiers()
    if unavailable:
        logger.warning(
            "Some agents unavailable: %s",
            ", ".join(f"{tier}" for tier in unavailable)
        )

    return True, ""
