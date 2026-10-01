"""Narrow compatibility fix for WorkBuddy authentication in FineSub 0.5.1."""

from __future__ import annotations


def _requires_login(text: str) -> bool:
    lowered = text.lower()
    return "authentication required" in lowered or "please use /login" in lowered


def install_workbuddy_auth_fix() -> None:
    from finesub.llm.agent.local_agent import (
        LocalAgentTransientError,
        LocalAgentUnavailableError,
        WorkBuddyLocalAgentDriver,
    )

    driver = WorkBuddyLocalAgentDriver
    if getattr(driver, "_yanami_auth_fix", False):
        return
    original_stream = driver._classify_stream_failure
    original_exit = driver._nonzero_exit

    def unavailable():
        return LocalAgentUnavailableError(
            "WorkBuddy authentication required：请打开 WorkBuddy 官方桌面客户端重新登录，"
            "确认同一账号/区域后重试。设置 → 本地 Agent 提供登录修复入口。"
        )

    def classify(self, normalized):
        error = original_stream(self, normalized)
        # Preserve the upstream model-entitlement and typed quota decisions.
        if isinstance(error, LocalAgentTransientError) and _requires_login(str(error)):
            return unavailable()
        return error

    def nonzero(self, capsule, return_code):
        error = original_exit(self, capsule, return_code)
        if isinstance(error, LocalAgentTransientError):
            try:
                with capsule.stderr_path.open("rb") as handle:
                    handle.seek(0, 2)
                    handle.seek(max(0, handle.tell() - 65_536))
                    stderr = handle.read().decode("utf-8", errors="replace")
            except OSError:
                stderr = ""
            if _requires_login(stderr):
                return unavailable()
        return error

    driver._classify_stream_failure = classify
    driver._nonzero_exit = nonzero
    driver._yanami_auth_fix = True
