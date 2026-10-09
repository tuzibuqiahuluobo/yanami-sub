"use client";

import { useState } from "react";
import { FolderOpen, ArrowRight, Check } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { KnowledgeSnapshot, TaskRequest, JobSnapshot, RefinedKnowledgeUpdateReport } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";
import { ConfirmDialog } from "./ConfirmDialog";

export function knowledgeOutcome(report: RefinedKnowledgeUpdateReport, zh: boolean): string {
  const labels = zh ? {
    generated: "提案已生成，尚未写入知识库", applied: "提案已提交，知识库已更新",
    partial: "仅部分修改提交成功，请查看报告", blocked: "修改未提交，请查看冲突或错误",
    no_change: "没有新增修改，知识库未变化", already_applied: "此提案已处理，不会重复提交",
  } : {
    generated: "Proposal generated; knowledge is unchanged", applied: "Proposal committed; knowledge updated",
    partial: "Only some changes committed; review the report", blocked: "Nothing committed; review conflicts or errors",
    no_change: "No new changes; knowledge is unchanged", already_applied: "Proposal already processed; no duplicate write",
  };
  return report.status ? labels[report.status] : (zh ? "操作完成，请查看报告" : "Operation finished; review the report");
}

export function ProposalReview({ report }: { report: RefinedKnowledgeUpdateReport }) {
  const { language } = useLanguage();
  return <div className="knowledge-proposal-review" aria-live="polite">
    <strong>{knowledgeOutcome(report, language === "zh")}</strong>
    <p className="field-hint">{[report.source, ...(Array.isArray(report.models) ? report.models : [])].filter(Boolean).join(" · ")}</p>
    {(report.chunks || []).map((chunk, index) => <pre key={index}>{String((chunk as { proposal_text?: string }).proposal_text || "")}</pre>)}
    {report.warnings?.map((warning) => <p className="field-hint" key={warning}>{warning}</p>)}
    {report.status !== "generated" ? <pre>{JSON.stringify(report.apply_reports || report, null, 2)}</pre> : null}
  </div>;
}

export function BilingualKnowledgeImport({ snapshot, tasks, onApplied }: {
  snapshot: KnowledgeSnapshot | null; tasks: JobSnapshot[]; onApplied: () => Promise<unknown>;
}) {
  const { language } = useLanguage();
  const zh = language === "zh";
  const [values, setValues] = useState({ source_srt: "", refined_srt: "", source_encoding: "auto", refined_encoding: "auto", subject: "", style_subject: "", prompt: "", task: "", llm_source: "auto", llm_agent: "", model: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [inspection, setInspection] = useState<RefinedKnowledgeUpdateReport | null>(null);
  const [proposal, setProposal] = useState<RefinedKnowledgeUpdateReport | null>(null);
  const [confirm, setConfirm] = useState(false);
  const update = (key: keyof typeof values, value: string) => { setValues((old) => ({ ...old, [key]: value })); setInspection(null); setProposal(null); setError(""); };
  const browse = async (key: "source_srt" | "refined_srt") => {
    try { const result = await desktopApi.selectSubtitleFile(); if (result.path) update(key, result.path); }
    catch (reason) { setError(String(reason)); }
  };
  const run = async (execute: boolean) => {
    setBusy(true); setError(""); setProposal(null);
    try {
      const inherited = tasks.find((task) => task.task_id === values.task)?.request;
      const request: Partial<TaskRequest> & { input: string } = inherited ? { ...inherited } : {
        input: values.source_srt, llm_source: values.llm_source as TaskRequest["llm_source"],
        llm_agent: values.llm_agent as TaskRequest["llm_agent"], llm_model: values.model.split(/[,，\n]/).map((id) => id.trim()).filter(Boolean),
      };
      const { source_srt, refined_srt, source_encoding, refined_encoding, subject, style_subject, prompt } = values;
      const report = await desktopApi.runBilingualKnowledgeUpdate({ source_srt, refined_srt, source_encoding, refined_encoding, subject, style_subject, prompt, request, execute });
      if (execute) setProposal(report); else setInspection(report);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const apply = async () => {
    setConfirm(false); if (!proposal?.draft_id) return;
    setBusy(true); setError("");
    try { setProposal(await desktopApi.applyKnowledgeProposal(proposal.draft_id)); await onApplied(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  return <section className="primary-panel knowledge-bilingual">
    <div className="section-heading"><div><span className="eyebrow">SRT → {zh ? "知识提案" : "knowledge proposal"}</span><h2>{zh ? "导入人工精修双语字幕" : "Import aligned bilingual subtitles"}</h2><p>{zh ? "不需要原任务或音视频。选择时间轴完全一致的原文与精修译文，先检查，再生成提案。" : "No original task or media required. Check matching original/refined timelines before generating a proposal."}</p></div></div>
    <fieldset disabled={busy} className="knowledge-form-grid">
      {(["source_srt", "refined_srt"] as const).map((key) => <label className="field" key={key}><span>{key === "source_srt" ? (zh ? "原文字幕（日文等）" : "Original subtitles") : (zh ? "人工精修译文（中文等）" : "Refined translation")}</span><div className="knowledge-file-row"><input value={values[key]} onChange={(event) => update(key, event.target.value)} placeholder=".srt" /><button type="button" className="button button-secondary" aria-label={zh ? "选择字幕文件" : "Choose subtitle file"} onClick={() => void browse(key)}><FolderOpen size={16} /></button></div><select aria-label={zh ? "字幕编码" : "Subtitle encoding"} value={values[key === "source_srt" ? "source_encoding" : "refined_encoding"]} onChange={(event) => update(key === "source_srt" ? "source_encoding" : "refined_encoding", event.target.value)}>{["auto", "utf-8-sig", "utf-16", "gb18030", "cp932"].map((encoding) => <option key={encoding} value={encoding}>{encoding === "auto" ? (zh ? "自动（UTF-8 / BOM）" : "Auto (UTF-8 / BOM)") : encoding.toUpperCase()}</option>)}</select></label>)}
      <label className="field"><span>{zh ? "目标知识条目" : "Target entry"}</span><select value={values.subject} onChange={(event) => update("subject", event.target.value)}><option value="">{zh ? "选择已创建的条目" : "Choose an existing entry"}</option>{snapshot?.entries.map((entry) => <option key={entry.id} value={entry.qualified_name}>{entry.qualified_name}</option>)}</select></label>
      <label className="field"><span>{zh ? "同时学习润色风格（可选）" : "Learn a style too (optional)"}</span><select value={values.style_subject} onChange={(event) => update("style_subject", event.target.value)}><option value="">{zh ? "不写入风格" : "Do not update a style"}</option>{snapshot?.entries.filter((entry) => entry.category === "style").map((entry) => <option key={entry.id} value={entry.qualified_name}>{entry.key}</option>)}</select></label>
      <label className="field field-span-all"><span>{zh ? "继承任务的模型选择" : "Inherit task model selection"}</span><select value={values.task} onChange={(event) => update("task", event.target.value)}><option value="">{zh ? "单独选择 API / Agent" : "Select API / Agent independently"}</option>{tasks.filter((task) => task.request).map((task) => <option value={task.task_id} key={task.task_id}>{task.request?.input.split(/[\\/]/).pop()}</option>)}</select></label>
      {!values.task ? <><label className="field"><span>{zh ? "模型来源" : "Model source"}</span><select value={values.llm_source} onChange={(event) => update("llm_source", event.target.value)}>{["auto", "api", "agent", "manual"].map((source) => <option key={source} value={source}>{source}</option>)}</select></label>{values.llm_source === "agent" ? <label className="field"><span>Agent</span><select value={values.llm_agent} onChange={(event) => update("llm_agent", event.target.value)}><option value="">{zh ? "按可用顺序尝试" : "Try available agents in order"}</option>{["LOCAL_AGY", "LOCAL_CLAUDE", "LOCAL_CODEX", "LOCAL_DSH", "LOCAL_WORKBUDDY"].map((agent) => <option key={agent}>{agent}</option>)}</select></label> : null}{values.llm_source === "manual" ? <label className="field"><span>{zh ? "模型 ID / knowledge=模型 ID" : "Model ID / knowledge=model ID"}</span><input value={values.model} onChange={(event) => update("model", event.target.value)} /></label> : null}</> : null}
      <label className="field field-span-all"><span>{zh ? "补充说明（可选）" : "Notes (optional)"}</span><textarea value={values.prompt} onChange={(event) => update("prompt", event.target.value)} /></label>
    </fieldset>
    {error ? <p role="alert" className="knowledge-error">{error}</p> : null}
    <div className="knowledge-actions"><button type="button" className="button button-secondary" disabled={busy || !values.source_srt || !values.refined_srt} onClick={() => void run(false)}><Check size={15} />{zh ? "检查时间轴（不调用模型）" : "Check timelines (no model call)"}</button><button type="button" className="button button-secondary" disabled={busy || !inspection || !values.subject} onClick={() => void run(true)}><ArrowRight size={15} />{zh ? "生成提案（会调用模型）" : "Generate proposal (model call)"}</button><button type="button" className="button button-primary" disabled={busy || proposal?.status !== "generated" || !proposal.proposal_count} onClick={() => setConfirm(true)}>{zh ? "应用已审阅提案" : "Apply reviewed proposal"}</button></div>
    {inspection ? <details className="knowledge-proposal-review" open><summary>{zh ? "已匹配字幕条数" : "Matched cues"}：{String(inspection.count)}</summary><pre>{JSON.stringify(inspection, null, 2)}</pre></details> : null}
    {proposal ? <ProposalReview report={proposal} /> : null}
    {busy ? <p role="status">{zh ? "正在处理，请稍候…" : "Working, please wait…"}</p> : null}
    <p className="field-hint">{zh ? "只提炼可复用术语、译名与表达习惯，不复制整份字幕，不作为 ASR 误听证据。提案文件保存在 knowledge-proposals，应用不会重新调用模型。" : "Extracts reusable terms and phrasing, not entire subtitles or ASR error evidence. Drafts are saved in knowledge-proposals; applying makes no model call."}</p>
    <ConfirmDialog config={{ id: "bilingual-apply", title: zh ? "提交这份提案？" : "Commit this proposal?", message: zh ? "将按当前审阅的内容写入所选条目。已有变更或冲突不会被强行覆盖。" : "Writes the reviewed changes to the selected entries without forcing conflicts.", allowRemember: false }} open={confirm} onConfirm={() => void apply()} onCancel={() => setConfirm(false)} />
  </section>;
}
