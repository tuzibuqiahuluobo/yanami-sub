"use client";

import { useEffect, useState } from "react";
import { desktopApi } from "@/lib/bridge";
import type { KnowledgeEntryDocument, KnowledgeSnapshot, KnowledgeStructurePreview } from "@/lib/types";
import { ConfirmDialog } from "./ConfirmDialog";
import { CustomSelect } from "./CustomSelect";
import { useLanguage } from "./LanguageProvider";

export function KnowledgeStructure({ document, entries, disabled, onChanged }: {
  document: KnowledgeEntryDocument; entries: KnowledgeSnapshot["entries"]; disabled: boolean; onChanged: () => Promise<void>;
}) {
  const { language } = useLanguage(); const en = language === "en";
  const [operation, setOperation] = useState("split");
  const [section, setSection] = useState(""); const [intro, setIntro] = useState("");
  const [destination, setDestination] = useState("");
  const [preview, setPreview] = useState<KnowledgeStructurePreview | null>(null);
  const [busy, setBusy] = useState(false); const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => { setPreview(null); }, [operation, section, intro, destination, document.revision, document.id]);
  const run = async (apply = false) => {
    setBusy(true); setNotice(""); setConfirm(false);
    try {
      const result = await desktopApi.knowledgeStructure(apply ? { apply: true, draft_id: preview!.draft_id } : {
        operation, entry: document.qualified_name, section, intro, to_entry: destination, expected_rev: document.revision,
      });
      if (apply) {
        setPreview(null);
        setNotice(`${en ? "Revision" : "修订"} ${result.revision} · ${en ? "applied operations" : "已应用操作"} ${result.applied ?? 0}${[...(result.rejected ?? []), ...(result.warnings ?? [])].length ? ` · ${[...(result.rejected ?? []), ...(result.warnings ?? [])].join("; ")}` : ""}`);
        await onChanged();
      } else setPreview(result);
    } catch (error) { setNotice(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  const sections = [...document.text.matchAll(/^##\s+(.+?)\s*$/gm)].map((match) => match[1]);
  return <details className="advanced-settings">
    <summary>{en ? "Restructure sections" : "整理小节结构"}</summary>
    <p className="field-help">{en ? "Moves the original lines with their IDs and history intact. Preview first, then confirm the same frozen operation. No model calls. Save your text edits first." : "保留原有行 ID 与历史，不删掉重建。先预览，再确认同一份冻结操作；不调用模型。请先保存正文修改。"}</p>
    <div className="field-grid">
      <div className="field"><span>{en ? "Action" : "操作"}</span><CustomSelect value={operation} disabled={busy || disabled} ariaLabel={en ? "Structure action" : "结构操作"} onChange={setOperation}
        options={[{ value: "split", label: en ? "Split into a sub-entry" : "拆成子条目" }, { value: "move", label: en ? "Move to another entry" : "移动到其他条目" }]} /></div>
      <div className="field"><span>{en ? "Section" : "小节"}</span><CustomSelect value={section} disabled={busy || disabled} ariaLabel={en ? "Section" : "小节"} onChange={setSection}
        options={[{ value: "", label: en ? "Choose a section" : "选择小节" }, ...sections.map((value) => ({ value, label: value }))]} /></div>
      {operation === "split" ? <label className="field field-wide"><span>{en ? "Sub-entry introduction" : "子条目简介"}</span><input value={intro} maxLength={2000} disabled={busy || disabled} onChange={(event) => setIntro(event.target.value)} /></label> :
        <div className="field field-wide"><span>{en ? "Destination" : "目标条目"}</span><CustomSelect value={destination} disabled={busy || disabled} ariaLabel={en ? "Destination entry" : "目标条目"} onChange={setDestination}
          options={[{ value: "", label: en ? "Choose an entry" : "选择条目" }, ...entries.filter((entry) => entry.id !== document.id && entry.category === document.category).map((entry) => ({ value: entry.qualified_name, label: entry.key }))]} /></div>}
    </div>
    <div className="task-actions"><button type="button" className="button button-secondary" disabled={busy || disabled || !section || !(operation === "split" ? intro.trim() : destination)} onClick={() => void run()}>{en ? "Preview structure change" : "预览结构变化"}</button>
      {preview ? <button type="button" className="button button-primary" disabled={busy || disabled} onClick={() => setConfirm(true)}>{en ? "Apply this preview" : "应用此预览"}</button> : null}</div>
    {preview ? <details><summary>{en ? `${preview.operations?.length ?? 0} engine operations` : `${preview.operations?.length ?? 0} 项引擎操作`}</summary><pre className="log-drawer">{JSON.stringify(preview.operations, null, 2)}</pre></details> : null}
    {notice ? <p className="field-help" role="status">{notice}</p> : null}
    <ConfirmDialog open={confirm} config={{ id: "knowledge-structure", title: en ? "Apply structure change?" : "确认整理结构？", message: `${document.qualified_name} / ${section}\n${en ? "The preview is refused if the knowledge revision changes." : "知识库修订变化时会拒绝应用，请重新预览。"}`, confirmLabel: en ? "Apply preview" : "应用预览" }} onConfirm={() => void run(true)} onCancel={() => setConfirm(false)} />
  </details>;
}
