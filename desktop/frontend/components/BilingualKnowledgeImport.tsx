"use client";

import { useEffect, useState } from "react";
import { saveUi, uiValue, workflowOptions } from "@/lib/preferences";
import { FolderOpen, ArrowRight, Check } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { KnowledgeSnapshot, TaskRequest, JobSnapshot, RefinedKnowledgeUpdateReport, RoutingSettings } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";
import { ConfirmDialog } from "./ConfirmDialog";
import { CustomSelect } from "./CustomSelect";

export function knowledgeOutcome(report: RefinedKnowledgeUpdateReport, zh: boolean): string {
  const labels = zh ? {
    generated: "提案已生成，尚未写入知识库", applied: "提案已提交，知识库已更新",
    partial: "仅部分修改提交成功，请查看报告", blocked: "修改未提交，请查看冲突或错误",
    no_change: "没有新增修改，知识库未变化", already_applied: "此提案已处理，不会重复提交",
    evidence_only: "条目未变化，已记录精修或风格证据",
  } : {
    generated: "Proposal generated; knowledge is unchanged", applied: "Proposal committed; knowledge updated",
    partial: "Only some changes committed; review the report", blocked: "Nothing committed; review conflicts or errors",
    no_change: "No new changes; knowledge is unchanged", already_applied: "Proposal already processed; no duplicate write",
    evidence_only: "Entries unchanged; refinement or style evidence recorded",
  };
  return report.status ? labels[report.status] : (zh ? "操作完成，请查看报告" : "Operation finished; review the report");
}

export function canApplyProposal(report: RefinedKnowledgeUpdateReport | null): boolean {
  return report?.status === "generated" && Boolean(report.draft_id && (report.proposal_count || report.has_feedback_evidence));
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

export function BilingualKnowledgeImport({ snapshot, tasks, onApplied, routing }: {
  snapshot: KnowledgeSnapshot | null; tasks: JobSnapshot[]; onApplied: () => Promise<unknown>; routing?: RoutingSettings;
}) {
  const { language } = useLanguage();
  const zh = language === "zh";
  const [values, setValues] = useState(() => ({ source_srt: "", refined_srt: "", subject: "", style_subject: "", prompt: "", task: "", ...workflowOptions("knowledgeImportOptions", { source_encoding: "auto", refined_encoding: "auto", llm_source: "auto", llm_agent: "", model: "" }) }));
  useEffect(() => {
    if (!uiValue("rememberLastSettings", true)) return;
    saveUi({ knowledgeImportOptions: { source_encoding: values.source_encoding, refined_encoding: values.refined_encoding, llm_source: values.llm_source, llm_agent: values.llm_agent, model: values.model } });
  }, [values.source_encoding, values.refined_encoding, values.llm_source, values.llm_agent, values.model]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [inspection, setInspection] = useState<RefinedKnowledgeUpdateReport | null>(null);
  const [proposal, setProposal] = useState<RefinedKnowledgeUpdateReport | null>(null);
  const [confirm, setConfirm] = useState(false);
  const agentTiers = ["LOCAL_AGY", "LOCAL_CLAUDE", "LOCAL_CODEX", "LOCAL_DSH", routing?.unified_llm_media ? "LOCAL_CODEBUDDY" : "LOCAL_WORKBUDDY"];
  const unsupportedAgent = !values.task && values.llm_source === "agent" && Boolean(values.llm_agent) && !agentTiers.includes(values.llm_agent);
  const update = (key: keyof typeof values, value: string) => { setValues((old) => ({ ...old, [key]: value })); setInspection(null); setProposal(null); setError(""); };
  const browse = async (key: "source_srt" | "refined_srt") => {
    try { const result = await desktopApi.selectSubtitleFile(); if (result.path) update(key, result.path); }
    catch (reason) { setError(String(reason)); }
  };
  const run = async (execute: boolean) => {
    if (execute && unsupportedAgent) return;
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
    <ol className="knowledge-steps" aria-label={zh ? "双语学习步骤" : "Bilingual learning steps"}><li>{zh ? "选择两份字幕" : "Choose both SRTs"}</li><li>{zh ? "检查时间轴" : "Check timelines"}</li><li>{zh ? "生成并审阅" : "Generate and review"}</li><li>{zh ? "确认写入" : "Apply changes"}</li></ol>
    <fieldset disabled={busy} className="knowledge-form-grid">
      {(["source_srt", "refined_srt"] as const).map((key) => {
        const title = key === "source_srt" ? (zh ? "原文字幕（日文等）" : "Original subtitles") : (zh ? "人工精修译文（中文等）" : "Refined translation");
        const encodingKey = key === "source_srt" ? "source_encoding" : "refined_encoding";
        return <div className="field" key={key}><span>{title}</span><div className="knowledge-file-row"><input aria-label={title} value={values[key]} onChange={(event) => update(key, event.target.value)} placeholder=".srt" /><button type="button" className="button button-secondary" aria-label={`${zh ? "选择" : "Choose"} ${title}`} onClick={() => void browse(key)}><FolderOpen size={16} /></button></div>
          <CustomSelect disabled={busy} ariaLabel={`${title} · ${zh ? "编码" : "encoding"}`} value={values[encodingKey]} onChange={(value) => update(encodingKey, value)} options={["auto", "utf-8-sig", "utf-16", "gb18030", "cp932"].map((value) => ({ value, label: value === "auto" ? (zh ? "自动（UTF-8 / BOM）" : "Auto (UTF-8 / BOM)") : value.toUpperCase() }))} /></div>;
      })}
      <div className="field"><span>{zh ? "目标知识条目" : "Target entry"}</span><CustomSelect disabled={busy} ariaLabel={zh ? "目标知识条目" : "Target entry"} value={values.subject} onChange={(value) => update("subject", value)} options={[{ value: "", label: zh ? "选择已创建的条目" : "Choose an existing entry" }, ...(snapshot?.entries || []).map((entry) => ({ value: entry.qualified_name, label: entry.qualified_name }))]} /></div>
      <div className="field"><span>{zh ? "同时学习润色风格（可选）" : "Learn a style too (optional)"}</span><CustomSelect disabled={busy} ariaLabel={zh ? "学习润色风格" : "Learn a style"} value={values.style_subject} onChange={(value) => update("style_subject", value)} options={[{ value: "", label: zh ? "不写入风格" : "Do not update a style" }, ...(snapshot?.entries || []).filter((entry) => entry.category === "style").map((entry) => ({ value: entry.qualified_name, label: entry.key }))]} /></div>
      {!snapshot?.entries.length ? <p className="field-hint field-span-all">{zh ? "尚无知识条目。请先到“条目”页新建一个目标，再回来生成提案。" : "No entries yet. Create a target under Entries before generating a proposal."}</p> : null}
      <div className="field field-span-all"><span>{zh ? "继承任务的模型选择" : "Inherit task model selection"}</span><CustomSelect disabled={busy} ariaLabel={zh ? "继承任务的模型选择" : "Inherit task model selection"} value={values.task} onChange={(value) => update("task", value)} options={[{ value: "", label: zh ? "单独选择 API / Agent" : "Select API / Agent independently" }, ...tasks.filter((task) => task.request && task.task_id).map((task) => ({ value: task.task_id!, label: `${task.request?.input.split(/[\\/]/).pop()} · ${task.task_id}` }))]} /></div>
      {!values.task ? <><div className="field"><span>{zh ? "模型来源" : "Model source"}</span><CustomSelect disabled={busy} ariaLabel={zh ? "模型来源" : "Model source"} value={values.llm_source} onChange={(value) => update("llm_source", value)} options={["auto", "api", "agent", "manual"].map((value) => ({ value, label: (zh ? { auto: "自动：API 优先，否则本地 Agent", api: "API 密钥", agent: "本地 Agent", manual: "手动指定模型 ID" } : { auto: "Auto: API, then local Agent", api: "API keys", agent: "Local Agent", manual: "Choose model ID" })[value]! }))} /></div>
        {values.llm_source === "agent" ? <div className="field"><span>Agent</span><CustomSelect disabled={busy} ariaLabel="Agent" value={unsupportedAgent ? "" : values.llm_agent} onChange={(value) => update("llm_agent", value)} options={[{ value: "", label: zh ? "按可用顺序尝试" : "Try available agents in order" }, ...agentTiers.map((value) => ({ value, label: value.replace("LOCAL_", "") }))]} /></div> : null}
        {values.llm_source === "manual" ? <label className="field"><span>{zh ? "模型 ID / knowledge=模型 ID" : "Model ID / knowledge=model ID"}</span><input value={values.model} onChange={(event) => update("model", event.target.value)} /></label> : null}</> : null}
      <label className="field field-span-all"><span>{zh ? "补充说明（可选）" : "Notes (optional)"}</span><textarea value={values.prompt} onChange={(event) => update("prompt", event.target.value)} /></label>
    </fieldset>
    {unsupportedAgent ? <p role="alert" className="knowledge-error">{zh ? "上次选择的 Agent 不适用于当前核心，请重新选择。不会自动切换到可能收费的 CodeBuddy。" : "The saved Agent is not supported by this core. Choose another; CodeBuddy will not be enabled automatically."}</p> : null}
    {error ? <p role="alert" className="knowledge-error">{error}</p> : null}
    <div className="knowledge-actions"><button type="button" className="button button-secondary" disabled={busy || !values.source_srt || !values.refined_srt} onClick={() => void run(false)}><Check size={15} />{zh ? "检查时间轴（不调用模型）" : "Check timelines (no model call)"}</button><button type="button" className="button button-secondary" disabled={busy || !inspection || !values.subject || unsupportedAgent} onClick={() => void run(true)}><ArrowRight size={15} />{zh ? "生成提案（会调用模型）" : "Generate proposal (model call)"}</button><button type="button" className="button button-primary" disabled={busy || !canApplyProposal(proposal)} onClick={() => setConfirm(true)}>{zh ? "应用已审阅提案" : "Apply reviewed proposal"}</button></div>
    <p className="field-hint" role="status">{!values.source_srt || !values.refined_srt ? (zh ? "下一步：选择原文和精修译文两份 SRT。" : "Next: choose the original and refined SRT files.") : !inspection ? (zh ? "下一步：点击“检查时间轴”。此步骤不调用模型、不写入知识库。" : "Next: check timelines. No model calls or knowledge writes.") : !values.subject ? (zh ? "下一步：选择要写入的目标知识条目。" : "Next: choose a target entry.") : !proposal ? (zh ? "下一步：生成提案（会调用模型），然后审阅内容。" : "Next: generate a proposal (model call), then review it.") : knowledgeOutcome(proposal, zh)}</p>
    {inspection ? <details className="knowledge-proposal-review" open><summary>{zh ? "已匹配字幕条数" : "Matched cues"}：{String(inspection.count)}</summary><pre>{JSON.stringify(inspection, null, 2)}</pre></details> : null}
    {proposal ? <ProposalReview report={proposal} /> : null}
    {busy ? <p role="status">{zh ? "正在处理，请稍候…" : "Working, please wait…"}</p> : null}
    <p className="field-hint">{zh ? "只提炼可复用术语、译名与表达习惯，不复制整份字幕，不作为 ASR 误听证据。提案文件保存在 knowledge-proposals，应用不会重新调用模型。" : "Extracts reusable terms and phrasing, not entire subtitles or ASR error evidence. Drafts are saved in knowledge-proposals; applying makes no model call."}</p>
    <ConfirmDialog config={{ id: "bilingual-apply", title: zh ? "提交这份提案？" : "Commit this proposal?", message: zh ? "将按当前审阅的内容写入所选条目。已有变更或冲突不会被强行覆盖。" : "Writes the reviewed changes to the selected entries without forcing conflicts.", allowRemember: false }} open={confirm} onConfirm={() => void apply()} onCancel={() => setConfirm(false)} />
  </section>;
}
