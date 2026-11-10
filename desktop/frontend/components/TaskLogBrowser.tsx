"use client";
import { useRef, useState } from "react";
import { FolderOpen, ScrollText } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { TaskLogLocation } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

const PAGE_SIZE = 10;

export function TaskLogBrowser({ tasksPath }: { tasksPath: string }) {
  const { language } = useLanguage();
  const en = language === "en";
  const [rows, setRows] = useState<TaskLogLocation[]>([]);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true); setError("");
    try { await action(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); }
    finally { setBusy(false); }
  };
  const refresh = async (requestedOffset = 0) => {
    const id = ++sequence.current;
    setBusy(true); setError("");
    try {
      let result = await desktopApi.listTaskLogs(query.trim(), requestedOffset);
      const page = Math.min(requestedOffset, Math.max(0, Math.ceil(result.total / PAGE_SIZE) - 1) * PAGE_SIZE);
      if (page !== requestedOffset) result = await desktopApi.listTaskLogs(query.trim(), page);
      if (id !== sequence.current) return;
      setRows(result.items); setTotal(result.total); setOffset(page);
    } catch (caught) {
      if (id === sequence.current) setError(caught instanceof Error ? caught.message : String(caught));
    } finally { if (id === sequence.current) setBusy(false); }
  };
  return <section className="settings-section task-log-browser">
    <div className="settings-section-heading"><div><h2>{en ? "Task logs" : "任务日志"}</h2>
      <p>{en ? "Find a task or batch, then open its log folder." : "按名称查找任务或批次，再打开对应日志所在的文件夹。"}</p></div>
      <button type="button" className="button button-secondary button-compact" disabled={busy} onClick={() => void run(() => desktopApi.openTasksDirectory())}><FolderOpen size={15} />{en ? "All task folders" : "所有任务目录"}</button>
    </div>
    <code className="system-logs-path">{tasksPath}</code>
    <details className="task-log-disclosure" onToggle={(event) => { if (event.currentTarget.open) void refresh(); }}>
      <summary><ScrollText size={16} aria-hidden="true" />{en ? "Browse task and batch logs · 10 per page" : "查看各任务与批次日志 · 每页 10 条"}</summary>
      <form className="log-browser-filter" onSubmit={(event) => { event.preventDefault(); void refresh(); }}>
        <label className="field"><span>{en ? "Task or batch name" : "任务或批次名称"}</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={en ? "Search logs" : "输入名称后搜索"} /></label>
        <button type="submit" className="button button-secondary" disabled={busy}>{en ? "Search / refresh" : "搜索 / 刷新"}</button>
      </form>
      <div className="log-location-list" aria-busy={busy}>
        {rows.map((row) => <article className="log-location-row" key={row.id}>
          <div><strong>{row.name}</strong><small>{row.batch ? en ? "Batch" : "批次" : en ? "Task" : "任务"} · {new Date(row.modified * 1000).toLocaleString(en ? "en-US" : "zh-CN")}</small><code>{row.log_path || (en ? "Log not created yet" : "尚未生成日志")}</code></div>
          <button type="button" className="button button-secondary button-compact" disabled={busy} onClick={() => void run(() => desktopApi.openTaskLogLocation(row.id))}><FolderOpen size={14} />{en ? "Open location" : "打开位置"}</button>
        </article>)}
        {!busy && !rows.length ? <p className="field-help">{en ? "No matching tasks or batches." : "没有匹配的任务或批次。"}</p> : null}
      </div>
      <nav className="log-browser-pagination" aria-label={en ? "Log pages" : "日志分页"}>
        <button type="button" className="button button-secondary button-compact" disabled={busy || offset === 0} onClick={() => void refresh(Math.max(0, offset - PAGE_SIZE))}>{en ? "Previous" : "上一页"}</button>
        <span role="status">{busy ? en ? "Loading…" : "正在读取…" : en ? `Page ${Math.floor(offset / PAGE_SIZE) + 1} / ${Math.max(1, Math.ceil(total / PAGE_SIZE))} · ${total} total` : `第 ${Math.floor(offset / PAGE_SIZE) + 1} / ${Math.max(1, Math.ceil(total / PAGE_SIZE))} 页 · 共 ${total} 条`}</span>
        <button type="button" className="button button-secondary button-compact" disabled={busy || offset + PAGE_SIZE >= total} onClick={() => void refresh(offset + PAGE_SIZE)}>{en ? "Next" : "下一页"}</button>
      </nav>
    </details>
    {error ? <p className="api-key-error" role="alert">{error}</p> : null}
  </section>;
}
