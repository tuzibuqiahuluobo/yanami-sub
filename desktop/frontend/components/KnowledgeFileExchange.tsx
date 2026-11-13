"use client";

import { useEffect, useState } from "react";
import { Download, FolderOpen, Upload } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { KnowledgeSnapshot } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";
import { CustomSelect } from "./CustomSelect";
import { ConfirmDialog } from "./ConfirmDialog";

export function KnowledgeFileExchange({ snapshot, selected, onSelect, busy, setBusy, onChanged }: {
  snapshot: KnowledgeSnapshot | null; selected: string; onSelect: (name: string) => void;
  busy: boolean; setBusy: (busy: boolean) => void; onChanged: () => Promise<void>;
}) {
  const { language } = useLanguage();
  const zh = language === "zh";
  const [file, setFile] = useState<{ path: string; text: string; base: string } | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  useEffect(() => { setFile(null); setMessage(""); setError(""); }, [selected]);
  const run = async (action: () => Promise<void>) => {
    setBusy(true); setError(""); setMessage("");
    try { await action(); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const choose = () => run(async () => {
    setFile(null);
    const result = await desktopApi.selectKnowledgeDocument();
    if (!result.path) return;
    const current = await desktopApi.getKnowledgeEntry(selected);
    if (result.text.match(/^#\s+(.+)$/m)?.[1].trim() !== current.key) {
      throw new Error(zh ? `文件的一级标题须为「# ${current.key}」。如为其他条目，请先在“条目”页创建同名目标。` : `The first heading must be "# ${current.key}". Create a matching target in Entries first.`);
    }
    setFile({ path: result.path, text: result.text, base: current.text });
  });
  const apply = () => run(async () => {
    if (!file) return;
    const current = await desktopApi.getKnowledgeEntry(selected);
    if (current.text !== file.base) throw new Error(zh ? "目标条目已变化，请重新选择文件并核对。" : "The target changed. Select and review the file again.");
    const result = await desktopApi.runKnowledgeMaintenance({ command: "edit", args: [selected], content: file.text });
    setFile(null); await onChanged();
    setMessage(`${zh ? "本地导入已完成（未调用模型、未上传）" : "Local import finished (no model call or upload)"}\n${result.output}`);
  });
  return <section className="primary-panel knowledge-section knowledge-file-exchange">
    <div className="section-heading"><div><h2>{zh ? "本地文件交换" : "Exchange a local file"}</h2><p>{zh ? "无需服务器、不调用模型。导出一个知识条目发给别人，或预览并导入收到的条目文件。" : "No server or model calls. Export one entry to send to someone, or review and import a received entry file."}</p></div></div>
    <p className="field-hint">{zh ? "1. 选择条目　→　2. 导出，或选择文件预览　→　3. 确认导入" : "1. Choose an entry → 2. Export, or select a file to review → 3. Confirm import"}</p>
    <div className="knowledge-action-grid"><div className="field"><span>{zh ? "导出条目 / 导入目标" : "Entry to export / target to update"}</span><CustomSelect value={selected} onChange={onSelect} disabled={busy} ariaLabel={zh ? "文件交换目标" : "File exchange target"} options={[{ value: "", label: zh ? "选择条目" : "Choose an entry" }, ...(snapshot?.entries || []).map(entry => ({ value: entry.qualified_name, label: entry.qualified_name }))]} /></div>
      <div className="knowledge-command-row"><button type="button" className="button button-secondary" disabled={busy || !selected} onClick={() => void run(async () => { const result = await desktopApi.exportKnowledgeEntry(selected); if (result.path) setMessage(`${zh ? "已导出：" : "Exported: "}${result.path}`); })}><Download size={15} />{zh ? "导出 .md 文件" : "Export .md"}</button>
      <button type="button" className="button button-secondary" disabled={busy || !selected} onClick={() => void choose()}><FolderOpen size={15} />{zh ? "选择文件并预览" : "Select and preview"}</button></div></div>
    <p className="field-hint">{zh ? "没有目标？先到“条目”页创建同名、同类别条目。导出包含正文，分享前请检查隐私。" : "No target yet? Create a matching name/category in Entries. Export includes entry text; review privacy before sharing."}</p>
    <details className="knowledge-source-editor"><summary>{zh ? "文件范围与导入注意事项" : "File scope and import notes"}</summary><p className="field-hint">{zh ? "仅交换 UTF-8 Markdown 条目正文，不含密钥、日志、任务或修订历史，不等同于完整备份。导入会修订目标，可能移除文件中未包含的内容；先核对预览。已有导出文件不会覆盖，请使用新文件名。" : "UTF-8 Markdown entry text only, not keys, logs, tasks or revision history; not a full backup. Import revises the target and may remove omitted content; review first. Existing exports are not overwritten; use a new name."}</p></details>
    {file ? <div className="knowledge-import-review"><strong>{file.path}</strong><pre tabIndex={0}>{file.text}</pre><p>{zh ? "导入会按上方内容修订目标条目，可能删除目标中未包含的内容；原版本可在修订历史中查看。仅导入可信文件。" : "Import revises the target to match this text and may remove omitted content; the previous revision remains in history. Import trusted files only."}</p><div className="knowledge-command-row"><button type="button" className="button button-primary" disabled={busy} onClick={() => setConfirming(true)}><Upload size={15} />{zh ? "确认导入目标条目" : "Import into target"}</button><button type="button" className="button button-secondary" disabled={busy} onClick={() => setFile(null)}>{zh ? "取消" : "Cancel"}</button></div></div> : null}
    {error ? <p className="knowledge-error" role="alert">{error}</p> : null}
    {message ? <p className="knowledge-file-result" role="status">{message}</p> : null}
    <ConfirmDialog open={confirming} config={{ id: "knowledge-file-import", title: zh ? "确认本地导入" : "Confirm local import", message: zh ? `用预览内容修订「${selected}」？目标中未包含的内容可能被移除，不会调用模型或上传文件。` : `Revise ${selected} with the preview? Omitted content may be removed. No model call or upload.`, allowRemember: false, tone: "danger" }} onCancel={() => setConfirming(false)} onConfirm={() => { setConfirming(false); void apply(); }} />
  </section>;
}
