"use client";
import { useEffect, useState } from "react";
import { desktopApi } from "@/lib/bridge";
import { saveUi, uiValue } from "@/lib/preferences";
import type { DiagnosticPackage, TaskLogLocation } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

export function Feedback() {
  const { language } = useLanguage();
  const en = language === "en";
  const [draft, setDraft] = useState(() => {
    const value = uiValue<{ title?: unknown; description?: unknown } | null>("feedbackDraft", null);
    return { title: typeof value?.title === "string" ? value.title.slice(0, 100) : "", description: typeof value?.description === "string" ? value.description.slice(0, 12000) : "" };
  });
  const [rows, setRows] = useState<TaskLogLocation[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [report, setReport] = useState<DiagnosticPackage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); } finally { setBusy(false); }
  };
  useEffect(() => {
    let active = true;
    void desktopApi.listTaskLogs().then((result) => {
      if (active) { setRows(result.items); setTotal(result.total); setSelected(result.items.filter((row) => row.log_path).slice(0, 1).map((row) => row.id)); }
    }).catch((caught) => { if (active) setError(String(caught)); });
    return () => { active = false; };
  }, []);
  const update = (patch: Partial<typeof draft>) => { const next = { ...draft, ...patch }; setDraft(next); saveUi({ feedbackDraft: next }); };
  const open = (browser: boolean) => run(async () => {
    await desktopApi.openFeedbackIssue(draft.title, draft.description, browser);
    setNotice(en ? "GitHub opened. Review and submit there; no Issue has been submitted by the app." : "已打开 GitHub，请在该页面检查并提交；应用尚未替你提交 Issue。");
  });
  return <div className="page feedback-page">
    <header className="page-header"><div><h1>{en ? "Feedback" : "反馈"}</h1><p>{en ? "Report bugs or ideas through GitHub Issues." : "通过 GitHub Issues 反馈问题或建议。"}</p></div></header>
    <section className="settings-section">
      <h2>{en ? "Describe the issue" : "描述问题"}</h2>
      <label className="field"><span>{en ? "Title" : "标题"}</span><input maxLength={100} value={draft.title} onChange={(event) => update({ title: event.target.value })} placeholder={en ? "What went wrong?" : "遇到了什么问题？"} /></label>
      <label className="field"><span>{en ? "Steps, expected result and actual result" : "重现步骤、预期结果与实际结果"}</span><textarea rows={6} maxLength={12000} value={draft.description} onChange={(event) => update({ description: event.target.value })} /></label>
      <p className="field-help">{en ? "GitHub requires your own account. Its native form supports Markdown, screenshots and video attachments. Only a short summary is prefilled; copy a longer description below." : "需登录你自己的 GitHub 账号。原生表单支持 Markdown、截图及视频附件。仅预填短摘要；较长描述请复制后粘贴。"}</p>
      <div className="feedback-actions"><button type="button" className="button button-primary" disabled={busy} onClick={() => void open(false)}>{en ? "New GitHub Issue" : "新建 GitHub Issue"}</button><button type="button" className="button button-secondary" disabled={busy} onClick={() => void open(true)}>{en ? "Continue in browser" : "在浏览器继续"}</button><button type="button" className="button button-secondary" disabled={busy || !draft.description} onClick={() => void run(async () => { await navigator.clipboard.writeText(draft.description); setNotice(en ? "Description copied." : "已复制完整描述。"); })}>{en ? "Copy description" : "复制完整描述"}</button></div>
      <p className="field-help">{en ? "If GitHub is unreachable, check your network or enable a proxy that can reach GitHub, then retry. The app does not change your proxy." : "无法连接 GitHub 时，请检查网络；仍无法反馈，建议开启可访问 GitHub 的代理再试。应用不会修改系统代理。"}</p>
    </section>
    <section className="settings-section">
      <h2>{en ? "Collect diagnostic logs" : "自动获取诊断日志"}</h2>
      <p className="field-help">{en ? "Creates a LOCAL redacted ZIP with selected task/batch logs, recent app/install/system logs and available update errors. No media, subtitles, credentials or Agent sessions are collected. Nothing is uploaded automatically." : "在本机生成脱敏 ZIP：所选任务/批次日志、近期应用/安装/系统日志及可用的更新错误。不会收集媒体、字幕、凭据或 Agent 会话，也不会自动上传。"}</p>
      <div className="feedback-log-list">{rows.map((row) => <label className="switch-row" key={row.id}><input type="checkbox" disabled={!row.log_path || busy} checked={selected.includes(row.id)} onChange={(event) => setSelected((current) => event.target.checked ? [...current, row.id].slice(0, 30) : current.filter((id) => id !== row.id))} /><span>{row.name}{row.batch ? en ? " · shared batch log" : " · 共享批次日志" : ""}{!row.log_path ? en ? " · no log" : " · 无日志" : ""}</span></label>)}</div>
      <div className="feedback-actions"><button type="button" className="button button-secondary button-compact" disabled={busy || offset === 0} onClick={() => void run(async () => { const next = Math.max(0, offset - 25); const result = await desktopApi.listTaskLogs("", next); setRows(result.items); setTotal(result.total); setOffset(next); })}>{en ? "Previous" : "上一页"}</button><span>{offset + rows.length} / {total}</span><button type="button" className="button button-secondary button-compact" disabled={busy || offset + 25 >= total} onClick={() => void run(async () => { const result = await desktopApi.listTaskLogs("", offset + 25); setRows(result.items); setTotal(result.total); setOffset(offset + 25); })}>{en ? "Next" : "下一页"}</button></div>
      <button type="button" className="button button-primary" disabled={busy} onClick={() => void run(async () => { setReport(await desktopApi.collectFeedbackLogs(selected)); setNotice(en ? "Local diagnostic package created. Review before uploading." : "已生成本地诊断包，请检查后再上传。"); })}>{busy ? en ? "Working…" : "正在处理…" : en ? "Collect logs locally" : "自动获取日志（本地）"}</button>
      {report ? <div className="feedback-report"><code className="system-logs-path">{report.path}</code><p className="field-help">{en ? "Public repository: attachments become public when selected for upload. Redaction may miss private free text. Open the ZIP and review every file before attaching it to GitHub." : "公开仓库：选择附件上传时就会公开。脱敏可能遗漏私人文本；请打开 ZIP 检查各文件，再选择上传到 GitHub。"}</p><div className="feedback-actions"><button type="button" className="button button-secondary" disabled={busy} onClick={() => void run(() => desktopApi.openFeedbackReport())}>{en ? "Open package location" : "打开诊断包位置"}</button><button type="button" className="button button-secondary" onClick={() => void run(async () => { await navigator.clipboard.writeText(report.path); setNotice(en ? "Package path copied." : "已复制诊断包路径。"); })}>{en ? "Copy path" : "复制路径"}</button></div><details><summary>{en ? "View collection report" : "查看收集报告"}</summary><pre>{report.report}</pre></details></div> : null}
    </section>
    {notice ? <p className="settings-section" role="status">{notice}</p> : null}
    {error ? <p className="api-key-error settings-section" role="alert">{error}</p> : null}
  </div>;
}
