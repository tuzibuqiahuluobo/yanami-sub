"use client";

import { useEffect, useState } from "react";
import { desktopApi } from "@/lib/bridge";
import { formatBytes } from "@/lib/formatters";
import { saveUi, uiValue } from "@/lib/preferences";
import type { DiagnosticPackage, FeedbackAttachment, TaskLogLocation } from "@/lib/types";
import { FieldHelp } from "./FieldHelp";
import { useLanguage } from "./LanguageProvider";

const LOG_PAGE_SIZE = 10;
const ATTACHMENT_LIMIT = 5;
const ATTACHMENT_BYTES = 2 * 1024 * 1024;
const IMAGE = /\.(png|jpe?g|webp)$/i;

function readAttachment(file: File): Promise<FeedbackAttachment> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取附件 / Could not read the attachment"));
    reader.onload = () => resolve({ name: file.name, data: String(reader.result).split(",", 2)[1] });
    reader.readAsDataURL(file);
  });
}

function Screenshot({ file }: { file: File }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  // Local file only; never a remote image or a submitted attachment URL.
  return src ? <img src={src} alt={file.name} /> : null;
}

export function Feedback() {
  const { language } = useLanguage();
  const text = (zh: string, en: string) => language === "en" ? en : zh;
  const [draft, setDraft] = useState(() => {
    const value = uiValue<Record<string, unknown> | null>("feedbackDraft", null);
    const get = (key: string, limit: number) => typeof value?.[key] === "string" ? value[key].slice(0, limit) : "";
    return { title: get("title", 100), actual: get("description", 6000), steps: get("steps", 4000), expected: get("expected", 4000) };
  });
  const [rows, setRows] = useState<TaskLogLocation[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [attachments, setAttachments] = useState<File[]>([]);
  const [systemLogs, setSystemLogs] = useState(false);
  const [report, setReport] = useState<DiagnosticPackage | null>(null);
  const [cli, setCli] = useState<Awaited<ReturnType<typeof desktopApi.feedbackCliStatus>>["mode"]>("missing");
  const [reviewed, setReviewed] = useState(false);
  const [published, setPublished] = useState("");
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
      if (active) { setRows(result.items); setTotal(result.total); }
    }).catch((caught) => { if (active) setError(String(caught)); });
    return () => { active = false; };
  }, []);
  const invalidate = () => { setReport(null); setReviewed(false); setPublished(""); setNotice(""); };
  const update = (patch: Partial<typeof draft>) => {
    const next = { ...draft, ...patch };
    invalidate();
    setDraft(next);
    saveUi({ feedbackDraft: { title: next.title, description: next.actual, steps: next.steps, expected: next.expected } });
  };
  const loadPage = (next: number) => run(async () => {
    const result = await desktopApi.listTaskLogs("", next);
    setRows(result.items); setTotal(result.total); setOffset(next);
  });
  const prepare = () => run(async () => {
    invalidate();
    const files = await Promise.all(attachments.map(readAttachment));
    setReport(await desktopApi.collectFeedbackLogs(selected, { ...draft, language }, files, systemLogs));
    void desktopApi.feedbackCliStatus().then((result) => setCli(result.mode)).catch(() => setCli("missing"));
  });
  const browser = () => run(async () => {
    if (!report) return;
    let copied = false;
    try { await navigator.clipboard.writeText(report.issue_markdown ?? ""); copied = true; } catch { /* Preview remains copyable. */ }
    await desktopApi.openFeedbackIssue(report.issue_title, "");
    setNotice(copied
      ? text("已复制完整正文并打开 GitHub。粘贴正文，选择要公开的附件，再提交。", "Full body copied. Paste it into GitHub, attach any files you want public, then submit.")
      : text("已打开 GitHub。从下方复制正文，粘贴到浏览器，再添加附件。", "GitHub opened. Copy the body below, paste it in the browser, then attach files."));
  });
  const publish = () => run(async () => {
    if (!reviewed || !report?.review_id || published) return;
    const result = await desktopApi.publishFeedbackIssue(report.review_id);
    setPublished(result.url);
    setNotice(result.attachments_complete
      ? text("Issue 已提交。完整 ZIP 如有需要可到 Issue 页面补传。", "Issue created. You can attach the full ZIP on its page if needed.")
      : text("Issue 已创建，但有截图上传失败。请打开该 Issue 补传，不要重复提交。", "Issue created, but some screenshots failed. Attach them to the existing issue rather than resubmitting."));
  });
  const canPublish = cli === "screenshots" || (cli === "text" && !report?.screenshots?.length);
  const setFiles = (incoming: File[]) => {
    if (!incoming.length || busy) return;
    if (incoming.some((file) => file.size === 0 || file.size > ATTACHMENT_BYTES || !/\.(png|jpe?g|webp|log|txt)$/i.test(file.name))
      || attachments.length + incoming.length > ATTACHMENT_LIMIT) {
      setError(text("最多选择 5 个 PNG、JPEG、WebP 截图或 TXT、LOG 日志，每个不超过 2 MiB。", "Select up to 5 PNG, JPEG, WebP, TXT or LOG files, 2 MiB each."));
      return;
    }
    invalidate(); setError(""); setAttachments((current) => [...current, ...incoming]);
  };
  return <div className="page feedback-page">
    <header className="page-header"><div><h1>{text("反馈", "Feedback")}</h1>
      <p>{text("描述问题、整理附件，审阅后提交到 GitHub。", "Describe the issue, prepare attachments, then review and publish on GitHub.")}</p></div></header>
    <fieldset className="feedback-fields" disabled={busy}>
      <section className="settings-section">
        <h2>{text("1. 描述问题", "1. Describe the issue")}</h2>
        <label className="field"><span>{text("标题（可自动拟定）", "Title (optional, generated if blank)")}</span>
          <input maxLength={100} value={draft.title} onChange={(event) => update({ title: event.target.value })} placeholder={text("一句话概括遇到的问题", "Summarize the problem in one sentence")} /></label>
        <label className="field"><span>{text("实际发生了什么", "What happened?")}</span>
          <textarea rows={3} maxLength={6000} value={draft.actual} onChange={(event) => update({ actual: event.target.value })} /></label>
        <div className="feedback-description-grid">
          <label className="field"><span>{text("重现步骤", "Steps to reproduce")}</span>
            <textarea rows={3} maxLength={4000} value={draft.steps} onChange={(event) => update({ steps: event.target.value })} /></label>
          <label className="field"><span>{text("预期结果", "Expected result")}</span>
            <textarea rows={3} maxLength={4000} value={draft.expected} onChange={(event) => update({ expected: event.target.value })} /></label>
        </div>
      </section>
      <section className="settings-section"
        onDragOver={(event) => { if (event.dataTransfer.types.includes("Files")) event.preventDefault(); }}
        onDrop={(event) => {
          if (!event.dataTransfer.files.length) return;
          event.preventDefault();
          setFiles(Array.from(event.dataTransfer.files));
        }}>
        <h2><FieldHelp label={text("2. 选择附件", "2. Select attachments")}
          hint={text("日志使用有大小上限的副本；截图会去除文件元数据，但不会遮盖画面里的隐私。", "Log snapshots are size-limited. Screenshot metadata is stripped, but visible private content is not hidden.")} /></h2>
        <p>{text("先在本机打包，不会自动上传。", "Packaging happens locally. Nothing is uploaded automatically.")}</p>
        <label className="field"><span>{text("选择或拖入截图与日志（可选）", "Choose or drop screenshots and logs (optional)")}</span>
          <input type="file" multiple accept=".png,.jpg,.jpeg,.webp,.txt,.log"
            onChange={(event) => { setFiles(Array.from(event.target.files ?? [])); event.currentTarget.value = ""; }} /></label>
        {attachments.length ? <ul className="feedback-attachments">{attachments.map((file, index) =>
          <li key={index}>{IMAGE.test(file.name) ? <Screenshot file={file} /> : null}
            <span>{file.name} · {formatBytes(file.size)}</span>
            <button type="button" className="button button-secondary button-compact" onClick={() => {
              invalidate(); setAttachments((current) => current.filter((_, item) => item !== index));
            }}>{text("移除", "Remove")}</button></li>)}</ul> : null}
        <details className="feedback-task-details">
          <summary>{text("选择已有任务或批次日志", "Choose existing task or batch logs")} · {selected.length}</summary>
          <div className="feedback-log-list">{rows.map((row) => <label className="switch-row" key={row.id}>
            <input type="checkbox" disabled={!row.log_path} checked={selected.includes(row.id)}
              onChange={(event) => { invalidate(); setSelected((current) => event.target.checked ? [...current, row.id].slice(0, 30) : current.filter((id) => id !== row.id)); }} />
            <span>{row.name}{row.batch ? text(" · 批次", " · Batch") : ""}{!row.log_path ? text(" · 无日志", " · No log") : ""}</span>
          </label>)}</div>
          <div className="feedback-actions">
            <button type="button" className="button button-secondary button-compact" disabled={offset === 0}
              onClick={() => void loadPage(offset - LOG_PAGE_SIZE)}>{text("上一页", "Previous")}</button>
            <span>{offset + rows.length} / {total}</span>
            <button type="button" className="button button-secondary button-compact" disabled={offset + LOG_PAGE_SIZE >= total}
              onClick={() => void loadPage(offset + LOG_PAGE_SIZE)}>{text("下一页", "Next")}</button>
          </div>
        </details>
        <label className="switch-row"><input type="checkbox" checked={systemLogs}
          onChange={(event) => { invalidate(); setSystemLogs(event.target.checked); }} />
          <span>{text("附带近期应用、安装和更新日志", "Include recent app, install and update logs")}</span></label>
        <button type="button" className="button button-primary task-generate" onClick={() => void prepare()}
          disabled={!draft.title.trim() && !draft.actual.trim() && !selected.length && !attachments.length && !systemLogs}>
          {busy ? text("正在处理…", "Working…") : text("生成报告并打包日志", "Prepare issue and package logs")}</button>
        {!report && error ? <p className="api-key-error" role="alert">{error}</p> : null}
      </section>
      {report ? <section className="settings-section feedback-report">
        <h2>{text("3. 审阅并提交", "3. Review and submit")}</h2>
        <p className="inline-note" role="note">{text("这是公开仓库，上传的附件未经登录也可查看。请检查正文、截图和 ZIP；脱敏不能识别所有私人内容。", "This repository is public. Review the body, screenshots and ZIP before uploading; redaction cannot find every secret.")}</p>
        <strong>{report.issue_title}</strong>
        <pre tabIndex={0}>{report.issue_markdown}</pre>
        <p>{text("完整诊断包仅保存在本机；直接提交只发送上面的正文和所选截图。ZIP 请在 GitHub 手动附上。", "The full ZIP is local. Direct publishing sends only the body above and selected screenshots. Attach the ZIP manually on GitHub.")}</p>
        <div className="feedback-actions">
          <button type="button" className="button button-secondary" onClick={() => void run(() => desktopApi.openFeedbackReport())}>
            {text("打开诊断包所在文件夹", "Open diagnostic folder")} · {formatBytes(report.size)}</button>
          <button type="button" className="button button-secondary" onClick={() => void run(async () => {
            await navigator.clipboard.writeText(report.issue_markdown ?? "");
            setNotice(text("已复制完整正文。", "Full issue body copied."));
          })}>{text("复制正文", "Copy issue body")}</button>
        </div>
        <details><summary>{text("查看收集清单", "See collected files")}</summary><pre>{report.report}</pre></details>
        {published && report.review_id ? <button type="button" className="button button-primary" onClick={() => void run(() => desktopApi.openPublishedFeedbackIssue(report.review_id!))}>
          {text("打开已创建的 Issue", "Open the published issue")}</button> : <>
          <div className="feedback-actions">
            <button type="button" className="button button-primary" onClick={() => void browser()}>{text("打开 GitHub 提交", "Continue on GitHub")}</button>
            {canPublish && report.review_id ? <>
              <label className="switch-row"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />
                <span>{text("我已检查正文和截图，同意公开", "I reviewed the body and screenshots and agree to publish")}</span></label>
              <button type="button" className="button button-secondary" disabled={!reviewed} onClick={() => void publish()}>
                {text("直接提交 Issue", "Publish issue directly")}</button>
            </> : null}
          </div>
          {!canPublish ? <p className="field-help">{text("没有可用的已登录 GitHub CLI，或其版本不支持截图。可继续在默认浏览器提交。", "A signed-in GitHub CLI with the required attachment support is unavailable. Continue in your default browser.")}</p> : null}
        </>}
        {notice ? <p role="status">{notice}</p> : null}
        {error ? <p className="api-key-error" role="alert">{error}</p> : null}
      </section> : null}
    </fieldset>
  </div>;
}
