"use client";

import { useState } from "react";
import { desktopApi } from "@/lib/bridge";
import type { CoreToolResult, DesktopApi } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

export function CoreToolsPanel({ mode }: { mode: "quota" | "glossaries" }) {
  const zh = useLanguage().language === "zh";
  const [data, setData] = useState<CoreToolResult>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState("");
  async function run(action: Parameters<DesktopApi["coreTool"]>[0], item?: string) {
    setBusy(true); setError(""); setPending("");
    try { setData(await desktopApi.coreTool(action, item)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  return <details className={mode === "quota" ? "settings-section settings-disclosure" : "primary-panel core-tools-panel"}>
    <summary>{mode === "quota" ? (zh ? "模型额度记录" : "Model quota history") : (zh ? "官方游戏术语表" : "Official game glossaries")}</summary>
    <p className="field-help">{mode === "quota"
      ? (zh ? "查看本机记录的额度暂缓与用量。解除暂缓只允许再次尝试，不会增加服务商额度。" : "Shows local usage and quota pauses. Resuming a key does not add provider quota.")
      : (zh ? "下载后，核心会按任务语境匹配相关游戏专名。下载术语表不调用模型。" : "The core matches installed terms to the task context. Fetching a glossary does not call a model.")}</p>
    <button type="button" className="button button-secondary" disabled={busy} onClick={() => void run(mode)}>
      {busy ? (zh ? "处理中…" : "Working…") : (zh ? "读取列表" : "Load list")}
    </button>
    {data?.games?.map(row => <div className="core-tool-row" key={row.name}><span>{row.name}</span>
      <button type="button" className="button button-secondary button-compact" disabled={busy || row.installed}
        onClick={() => void run("fetch_glossary", row.name)}>{row.installed ? (zh ? "已安装" : "Installed") : (zh ? "下载" : "Download")}</button>
    </div>)}
    {data?.rows?.map(row => <div className="core-tool-row" key={row.id}>
      <span><strong>{row.id}</strong><br />
        {row.until ? new Date(row.until).toLocaleString() : null}
        {row.calls !== undefined ? ` · ${row.calls} ${zh ? "次调用" : "calls"} · ${((row.seconds ?? 0) / 60).toFixed(1)} min` : null}
      </span>
      {row.spent ? <button type="button" className="button button-secondary button-compact" disabled={busy}
        onClick={() => pending === row.id ? void run("thaw_quota", row.id) : setPending(row.id)}>
        {pending === row.id ? (zh ? "确认解除暂缓" : "Confirm resume") : (zh ? "解除暂缓" : "Resume attempts")}
      </button> : null}
    </div>)}
    {data && !data.games?.length && !data.rows?.length ? <p className="field-help" role="status">{zh ? "暂无记录。" : "No records."}</p> : null}
    {error ? <p className="api-key-error" role="alert">{error}</p> : null}
  </details>;
}
