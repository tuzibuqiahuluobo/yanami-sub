from types import SimpleNamespace

from finesub.llm.agent.local_agent import (
    LocalAgentPolicyViolationError, LocalAgentTransientError,
    LocalAgentUnavailableError, WorkBuddyLocalAgentDriver,
)
from desktop.backend.worker.workbuddy_compat import install_workbuddy_auth_fix


def test_workbuddy_structured_auth_is_unavailable_not_retryable():
    install_workbuddy_auth_fix()
    driver = WorkBuddyLocalAgentDriver()
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


def test_workbuddy_model_entitlement_and_network_classification_are_preserved():
    install_workbuddy_auth_fix()
    driver = WorkBuddyLocalAgentDriver()
    assert isinstance(driver._classify_stream_failure([
        {"event": "result", "error": "model is not supported (authentication required)", "category": "auth"}
    ]), LocalAgentPolicyViolationError)
    assert isinstance(driver._classify_stream_failure([
        {"event": "result", "error": "connection reset by peer"}
    ]), LocalAgentTransientError)


def test_workbuddy_nonzero_auth_stderr(tmp_path):
    install_workbuddy_auth_fix()
    stderr = tmp_path / "stderr.log"
    stderr.write_text("Authentication required. Please use /login", encoding="utf-8")
    capsule = SimpleNamespace(stderr_path=stderr, episode_id="test")
    assert isinstance(WorkBuddyLocalAgentDriver()._nonzero_exit(capsule, 1), LocalAgentUnavailableError)
