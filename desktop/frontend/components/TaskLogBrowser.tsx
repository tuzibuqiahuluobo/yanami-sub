"use client";
import { useState } from "react";
import { desktopApi } from "@/lib/bridge";
import type { TaskLogLocation } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

export function TaskLogBrowser({ tasksPath }: { tasksPath: string }) {
  const { language } = useLanguage();
  const en = language === "en";
  const [rows, setRows] = useState<TaskLogLocation[]>([]);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const run = async (action: () => Promise<unknown>) => { setBusy(true); setError(""); try { await action(); } catch (caught) { setError(caught instanceof Error ? caught.message : String(caught)); } finally { setBusy(false); } };
  const refresh = (page = 0) => run(async () => { const result = await desktopApi.listTaskLogs(query, page); setRows(result.items); setTotal(result.total); setOffset(page); });
  return <section className="settings-section task-log-browser">
    <h2>{en ? "Task logs" : "任务日志"}</h2>
    <code className="system-logs-path">{tasksPath}</code>
    <button type="button" className="button button-secondary" disabled={busy} onClick={() => void run(() => desktopApi.openTasksDirectory())}>{en ? "Open all task folders" : "打开所有任务目录"}</button>
    <details onToggle={(event) => { if (event.currentTarget.open) void refresh(); }}><summary>{en ? "Browse task and batch logs" : "查看各任务与批次日志"}</summary>
      <div className="log-browser-filter"><label className="field"><span>{en ? "Filter by name" : "按名称筛选"}</span><input value={query} onChange={(event) => setQuery(event.target.value)} /></label><button type="button" className="button button-secondary" disabled={busy} onClick={() => void refresh()}>{en ? "Refresh" : "刷新"}</button></div>
      {rows.map((row) => <div className="log-location-row" key={row.id}><div><strong>{row.name}</strong><small>{row.batch ? en ? "Shared batch log" : "共享批次日志" : en ? "Task log" : "任务日志"} · {new Date(row.modified * 1000).toLocaleString()}</small><code>{row.log_path || (en ? "Log not created" : "尚未生成日志")}</code></div><button type="button" className="button button-secondary button-compact" disabled={busy} onClick={() => void run(() => desktopApi.openTaskLogLocation(row.id))}>{en ? "Open location" : "打开位置"}</button></div>)}
      {!busy && !rows.length ? <p className="field-help">{en ? "No matching tasks." : "没有匹配的任务。"}</p> : null}
      <div className="log-browser-filter"><button type="button" className="button button-secondary button-compact" disabled={busy || offset === 0} onClick={() => void refresh(Math.max(0, offset - 25))}>{en ? "Previous" : "上一页"}</button><span>{offset + rows.length} / {total}</span><button type="button" className="button button-secondary button-compact" disabled={busy || offset + 25 >= total} onClick={() => void refresh(offset + 25)}>{en ? "Next" : "下一页"}</button></div>
    </details>{error ? <p className="api-key-error" role="alert">{error}</p> : null}
  </section>;
}
