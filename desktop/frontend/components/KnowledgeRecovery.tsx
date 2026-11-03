"use client";

import { useState } from "react";
import { desktopApi } from "@/lib/bridge";
import type { KnowledgeRecoveryResult } from "@/lib/types";
import { ConfirmDialog } from "./ConfirmDialog";
import { CustomSelect } from "./CustomSelect";
import { useLanguage } from "./LanguageProvider";

export function KnowledgeRecovery({ onChanged }: { onChanged: () => Promise<unknown> }) {
  const { language } = useLanguage(); const en = language === "en";
  const [backups, setBackups] = useState<NonNullable<KnowledgeRecoveryResult["backups"]>>([]);
  const [selected, setSelected] = useState("");
  const [prepared, setPrepared] = useState<KnowledgeRecoveryResult | null>(null);
  const [outcome, setOutcome] = useState<KnowledgeRecoveryResult | null>(null);
  const [busy, setBusy] = useState(false); const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState(false);
  const run = async (action: "list" | "prepare" | "activate" | "recover") => {
    setBusy(true); setNotice(""); setConfirm(false);
    try {
      const result = await desktopApi.knowledgeRecovery(action, action === "activate" ? prepared!.token! : selected, action === "activate" || action === "recover");
      if (action === "list") { setBackups(result.backups ?? []); setPending(Boolean(result.pending)); if (!result.backups?.length) setNotice(en ? "No local migration restore points found." : "未发现本机迁移恢复点。"); }
      if (action === "prepare") { setPrepared(result); setOutcome(null); }
      if (action === "activate") { setPrepared(null); setOutcome(result); await onChanged(); }
      if (action === "recover") { setPending(false); setPrepared(null); setNotice(result.note ?? ""); await onChanged(); }
    } catch (error) { setNotice(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  return <section className="primary-panel knowledge-section">
    <div className="section-heading"><div><h2>{en ? "Knowledge restore points" : "知识库恢复点"}</h2><p>{en ? "Local migration snapshots only. Prepare and verify a separate copy before activation; configuration and keys are never restored." : "仅使用本机迁移快照。先校验并准备独立副本，再启用；不恢复配置和密钥。"}</p></div></div>
    <div className="field-grid">
      <div className="field field-wide"><span>{en ? "Restore point (verified when prepared)" : "恢复点（准备时验证完整性）"}</span><CustomSelect value={selected} disabled={busy} ariaLabel={en ? "Knowledge restore point" : "知识库恢复点"} onChange={(value) => { setSelected(value); setPrepared(null); }}
        options={[{ value: "", label: en ? "Select a restore point" : "选择恢复点" }, ...backups.map((backup) => ({ value: backup.id, label: `${backup.created_at} · schema ${backup.schema_version} · ${backup.files} files` }))]} /></div>
    </div>
    {pending ? <div className="inline-note"><span>{en ? "An interrupted restore prevents opening an empty store." : "检测到未完成的恢复，已阻止创建空知识库。"}</span><button type="button" className="button button-secondary" disabled={busy} onClick={() => void run("recover")}>{en ? "Settle interrupted restore" : "修复未完成的恢复"}</button></div> : null}
    <div className="knowledge-actions"><button type="button" className="button button-secondary" disabled={busy} onClick={() => void run("list")}>{en ? "Find restore points" : "查找恢复点"}</button><button type="button" className="button button-secondary" disabled={busy || !selected} onClick={() => void run("prepare")}>{busy ? (en ? "Working…" : "处理中…") : (en ? "Verify and prepare copy" : "校验并准备副本")}</button>
      {prepared?.token ? <button type="button" className="button button-primary" disabled={busy} onClick={() => setConfirm(true)}>{en ? "Activate prepared copy" : "启用已准备的副本"}</button> : null}</div>
    {prepared ? <div className="inline-note"><span>{prepared.note}<br />{en ? "Entries" : "条目"} {prepared.entries} · rev {prepared.revision}<code className="result-path">{prepared.path}</code></span></div> : null}
    {outcome?.activated ? <div className="inline-note" role="status"><span>{outcome.note}<code className="result-path">{outcome.rollback_backup || outcome.previous}</code></span></div> : null}
    {notice ? <p className="field-help" role="status">{notice}</p> : null}
    <ConfirmDialog open={confirm} config={{ id: "knowledge-recovery", title: en ? "Activate this restore point?" : "启用此恢复点？", message: en ? "All tasks must be idle. Current knowledge is backed up first and retained separately; old proposals are quarantined, not applied to the restored base. Changes since preparation make this operation fail safely." : "必须先结束所有任务。当前知识库会先备份并另行保留；旧提案会隔离保存，不会套用到恢复后的知识库。准备后数据如有变化，将安全拒绝本次操作。", confirmLabel: en ? "Activate restore point" : "启用恢复点", tone: "danger" }} onConfirm={() => void run("activate")} onCancel={() => setConfirm(false)} />
  </section>;
}
