from types import SimpleNamespace

import pytest

from finesub.llm.agent import local_agent
from finesub.llm.agent.local_agent import (
    LocalAgentPolicyViolationError, LocalAgentTransientError,
    LocalAgentUnavailableError,
)
from desktop.backend.worker.workbuddy_compat import install_workbuddy_auth_fix


@pytest.fixture
def driver():
    legacy = getattr(local_agent, "WorkBuddyLocalAgentDriver", None)
    if legacy is None:
        pytest.skip("0.6.0 replaced WorkBuddy; the old-core shim is not used")
    return legacy()


def test_workbuddy_structured_auth_is_unavailable_not_retryable(driver):
    install_workbuddy_auth_fix()
    error = driver._classify_stream_failure([{
        "event": "result", "error": "Authentication required. Please use /login command to sign in",
        "terminal_reason": "error_during_execution",
    }])
    assert isinstance(error, LocalAgentUnavailableError)
    assert "官方桌面客户端" in str(error)
    install_workbuddy_auth_fix()  # idempotent
    assert isinstance(driver._classify_stream_failure([
        {"event": "result", "error": "Authentication required"}
    ]), LocalAgentUnavailableError)


def test_workbuddy_model_entitlement_and_network_classification_are_preserved(driver):
    install_workbuddy_auth_fix()
    assert isinstance(driver._classify_stream_failure([
        {"event": "result", "error": "model is not supported (authentication required)", "category": "auth"}
    ]), LocalAgentPolicyViolationError)
    assert isinstance(driver._classify_stream_failure([
        {"event": "result", "error": "connection reset by peer"}
    ]), LocalAgentTransientError)


def test_workbuddy_nonzero_auth_stderr(tmp_path, driver):
    install_workbuddy_auth_fix()
    stderr = tmp_path / "stderr.log"
    stderr.write_text("Authentication required. Please use /login", encoding="utf-8")
    capsule = SimpleNamespace(stderr_path=stderr, episode_id="test")
    assert isinstance(driver._nonzero_exit(capsule, 1), LocalAgentUnavailableError)


def test_new_core_never_imports_or_patches_the_retired_workbuddy_driver(monkeypatch):
    class ModernDriver:
        pass

    monkeypatch.delattr(local_agent, "WorkBuddyLocalAgentDriver", raising=False)
    monkeypatch.setattr(local_agent, "CodeBuddyLocalAgentDriver", ModernDriver, raising=False)
    install_workbuddy_auth_fix()
    assert vars(ModernDriver).keys().isdisjoint({"_yanami_auth_fix", "_classify_stream_failure", "_nonzero_exit"})
