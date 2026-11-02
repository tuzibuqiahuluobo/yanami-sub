"use client";

import { useRef, useState } from "react";
import { desktopApi } from "@/lib/bridge";
import type { ConfigMigrationPlan, ConfigMigrationResult } from "@/lib/types";
import { ConfirmDialog, type ConfirmDialogConfig } from "./ConfirmDialog";
import { useLanguage } from "./LanguageProvider";

export function migrationConfirmation(plan: ConfigMigrationPlan, language: string): ConfirmDialogConfig {
  const zh = language === "zh";
  return {
    id: "core-media-migration",
    allowRemember: false,
    title: zh ? "备份并转换这份配置？" : "Back up and convert this configuration?",
    message: (zh ? "先备份原配置及现有的自定义模型清单，再应用以下更改；不切换模型、不启动任务。\n" :
      "Back up the config and any custom model catalog, then apply only these changes. No model switch or task run.\n") +
      plan.config_path + "\n" + plan.changes.join("; "),
    confirmLabel: zh ? "备份并应用" : "Back up and apply",
    cancelLabel: zh ? "取消" : "Cancel",
  };
}

export function ConfigMigration({ onApplied }: { onApplied?: () => Promise<void> }) {
  const { language } = useLanguage();
  const zh = language === "zh";
  const [plan, setPlan] = useState<ConfigMigrationPlan | null>(null);
  const [result, setResult] = useState<ConfigMigrationResult | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);

  async function preview() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError(""); setResult(null); setPlan(null);
    try { setPlan(await desktopApi.previewConfigMigration()); }
    catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { inFlight.current = false; setBusy(false); }
  }

  async function apply() {
    if (inFlight.current || !plan || plan.status !== "ready") return;
    inFlight.current = true; setBusy(true); setConfirm(false); setError("");
    try {
      const applied = await desktopApi.applyConfigMigration(plan.token, true);
      setResult(applied); setPlan(null);
      try { await onApplied?.(); }
      catch { setError(zh ? "配置已更新，但界面刷新失败；请重启应用。" : "Config updated, but the view could not refresh. Restart the app."); }
    } catch (failure) {
      setPlan(null);  // A stale or blocked preview must be regenerated.
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally { inFlight.current = false; setBusy(false); }
  }

  return <div className="routing-config-migration">
    <div className="routing-actions">
      <span>{zh ? "旧版配置转换" : "Legacy configuration conversion"}</span>
      <button type="button" className="button button-secondary button-compact" disabled={busy} onClick={() => void preview()}>
        {busy ? (zh ? "正在处理…" : "Working…") : (zh ? "预览转换" : "Preview conversion")}
      </button>
    </div>
    <p className="field-hint">{zh ? "只转换明确的媒体设置；预览不改文件，应用前备份。冲突和失效模型需人工审阅。" :
      "Convert only unambiguous media settings. Preview is read-only; Apply keeps a backup. Conflicts and retired models require review."}</p>
    {plan ? <div aria-live="polite">
      <code style={{ overflowWrap: "anywhere" }}>{plan.config_path}</code>
      {plan.changes.length ? <><p>{zh ? "拟更改（尚未写入）" : "Proposed changes (not applied)"}</p>
        <ul>{plan.changes.map((change) => <li key={change}>{change}</li>)}</ul></> : null}
      {plan.issues.map((issue) => <p className="routing-error" key={issue}>{issue}</p>)}
      {plan.status === "ready" ? <button type="button" className="button button-primary button-compact" disabled={busy} onClick={() => setConfirm(true)}>
        {zh ? "确认更改…" : "Review and confirm…"}
      </button> : plan.status === "current" ? <p>{zh ? "没有需要转换的旧媒体设置。" : "No legacy media settings to convert."}</p>
        : plan.status === "legacy" ? <p>{zh ? "当前内核尚不启用此转换。" : "Conversion is not enabled for this core."}</p> : null}
    </div> : null}
    {result ? <p role="status">{zh ? "配置已更新。私有备份：" : "Configuration updated. Private backup: "}<code style={{ overflowWrap: "anywhere" }}>{result.backup_path}</code>
      {result.restart_required ? (zh ? " 请重启应用以刷新运行配置。" : " Restart the app to refresh the runtime configuration.") : null}</p> : null}
    {error ? <p className="routing-error" role="alert">{error}</p> : null}
    {plan ? <ConfirmDialog config={migrationConfirmation(plan, language)} open={confirm} onConfirm={() => void apply()} onCancel={() => setConfirm(false)} /> : null}
  </div>;
}
