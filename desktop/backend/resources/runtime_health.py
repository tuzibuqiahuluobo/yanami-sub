"""Desktop scheduling for the core's managed-runtime checks; no second checker."""
from __future__ import annotations

import threading

from desktop.backend.common.models import BridgeError


class RuntimeHealth:
    def __init__(self, runtime):
        self.runtime = runtime
        self.reason = ""
        self.report = None
        self.detail = ""
        self._lock = threading.RLock()

    @property
    def enabled(self):
        return getattr(self.runtime, "development_python", None) is None and all(
            callable(getattr(self.runtime, name, None)) for name in ("condition", "check", "refuse_if_in_use"))

    @property
    def version(self):
        try:
            return (self.runtime.app_source / "VERSION").read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            return ""  # Without an identity the core deliberately checks every run.

    def policy(self):
        from finesub.config import read_config_with_path
        from finesub_bootstrap.runtime_health import INTEGRITY_CHECK_VALUES, RuntimeSettings
        from desktop.backend.settings.config_file import shared_config_path

        # Bootstrap's reader only accepts <directory>/config.toml. The desktop
        # also accepts explicit filenames, so parse via the shared core reader.
        data, _path = read_config_with_path(shared_config_path(self.runtime.paths.user_data))
        section = data.get("runtime", {})
        default = RuntimeSettings()
        if not isinstance(section, dict):
            raise ValueError("[runtime] 必须是配置表 / runtime must be a table")
        check = section.get("integrity_check", default.integrity_check)
        repair = section.get("auto_repair", default.auto_repair)
        if not isinstance(check, str) or check not in INTEGRITY_CHECK_VALUES or not isinstance(repair, bool):
            raise ValueError("请检查 [runtime] integrity_check / auto_repair；未自动重建 / Invalid runtime policy")
        return RuntimeSettings(integrity_check=check, auto_repair=repair)

    def assess(self, *, explicit=False, after_failure=False) -> BridgeError | None:
        if not self.enabled:
            return None
        from finesub_bootstrap.runtime_health import should_check_before_run

        with self._lock:
            try:
                policy = self.policy()
                reason = self.runtime.condition()
                if reason not in {"ready", "absent", "outdated", "damaged"}:
                    raise RuntimeError(f"Unknown runtime condition: {reason}")
                report = None
                check = explicit or (policy.integrity_check != "off" and (after_failure or self.reason or should_check_before_run(
                    policy.integrity_check, self.runtime.runtime_root, self.version)))
                if reason == "ready" and not check and self.reason:
                    reason, report = self.reason, self.report
                elif reason == "ready" and check:
                    report = self.runtime.check()
                    if report is None:
                        raise RuntimeError("无法按依赖锁核对运行环境 / Runtime lock could not be checked")
                    if report.mismatched:
                        reason = "mismatched"
                self.reason = "" if reason in {"ready", "absent"} else reason
                self.report = report
                problems = report.problems() if report is not None else []
                self.detail = "；".join(problems) or (
                    self.runtime.health_detail() if reason == "damaged" else reason
                )
                if self.reason and not explicit and not policy.auto_repair:
                    return BridgeError(code="runtime_repair_disabled",
                        message="运行环境需要修复，但已关闭自动重建。请在资源页检查后手动安装/修复。 / Automatic runtime repair is disabled",
                        action="open_resources")
            except (OSError, ValueError, RuntimeError) as error:
                self.reason, self.detail = "check_failed", str(error)
                return BridgeError(code="runtime_check_failed", message=str(error), action="open_resources")
        return None

    def failure_note(self) -> str:
        if not self.enabled:
            return ""
        try:
            error = self.assess(after_failure=True)
            with self._lock:
                reason, report, detail = self.reason, self.report, self.detail
            if error is not None:
                return f"Warning: 任务失败后的环境核对 / Post-failure runtime check: {error.message}"
            if reason or detail == "absent":
                return f"Warning: 运行环境需要修复，请在资源页检查；未自动重装或重跑任务 / Runtime requires repair: {detail}"
            if report is None:
                return "按设置跳过失败后的逐文件核对 / Post-failure file check skipped by policy"
            return "失败后核对未发现依赖缺失或版本不一致；原任务错误保持不变 / Runtime file check passed; original task error retained"
        except Exception as error:
            return f"Warning: 失败后环境核对未完成，未自动重装 / Runtime check could not finish: {error}"

    def status(self, value):
        # Polling only projects cached facts; it never hashes, probes or installs.
        with self._lock:
            if self.reason:
                return value.model_copy(update={"state": "failed",
                    "detail": f"运行环境需要核对/修复 / Runtime requires repair: {self.detail}"})
        return value

    def install_options(self, *, stage=None, log=None, automatic=False):
        if not self.enabled:
            return {}
        error = self.assess(explicit=not automatic)
        if error is not None:
            raise RuntimeError(error.message)
        self.runtime.refuse_if_in_use()  # GUI installer holds no worker lease.
        with self._lock:
            reason, report, detail = self.reason, self.report, self.detail
        if reason:
            if report is None:
                report = self.runtime.check()
            message = f"将按依赖锁重建运行环境，不更改任务/知识库 / Rebuilding managed runtime: {detail}"
            if stage is not None:
                stage("repairing_runtime", message)
            if log is not None:
                log(message)
                if report is not None:
                    for loss in report.losses(include_versions=reason != "outdated"):
                        log(f"重建将移除 / Removed by rebuild: {loss}")
                else:
                    log("无法读取原环境的完整包清单 / Existing package inventory is unavailable")
        return {"force": bool(reason), "verify_hashes": bool(reason)}

    def installed(self):
        with self._lock:
            self.reason, self.detail, self.report = "", "", None
