"use client";

import { useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { AgentCooperationResult } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

export function AgentCooperation() {
  const { language } = useLanguage();
  const en = language === "en";
  const [rows, setRows] = useState<NonNullable<AgentCooperationResult["assignments"]>>([]);
  const [joined, setJoined] = useState<AgentCooperationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);
  const run = async (action: "list" | "join", assignment?: string) => {
    setBusy(true); setNotice("");
    try {
      const result = await desktopApi.agentCooperation({ action, assignment,
        worker: joined && assignment === joined.assignment ? joined.worker : undefined });
      if (action === "list") { setRows(result.assignments ?? []); setLoaded(true); }
      else setJoined(result);
    } catch (error) { setNotice(error instanceof Error ? error.message : String(error)); }
    finally { setBusy(false); }
  };
  return <details className="advanced-settings agent-cooperation">
    <summary>{en ? "Agent cooperation (experimental)" : "Agent 协作（实验性）"}</summary>
    <p className="field-help">{en ? "Choose manual routing → conversational-agent and text media to hand text work to your own Agent session. Wait for speech processing to finish, then refresh here. This frozen upstream protocol waits up to one hour for a worker; it does not launch or message your Agent." : "选择手动路由 → conversational-agent，并使用纯文本媒体，将文字任务交给你自己的 Agent 会话。语音处理完成后在这里刷新。沿用上游已冻结的协议，最多等待一小时接入；应用不会自动启动或向 Agent 发消息。"}</p>
    <button type="button" className="button button-secondary button-compact" disabled={busy} onClick={() => void run("list")}><RefreshCw size={14} />{en ? "Find waiting assignments" : "查找等待中的协作任务"}</button>
    {loaded && !rows.length ? <p className="field-help">{en ? "No open assignment in this installation. It appears only when the first text model call is queued." : "当前安装尚无待接入任务；只有首次文字模型调用入队后才会出现。"}</p> : null}
    {rows.map((row) => <div className="agent-status-row" key={row.id}>
      <div><strong>{row.id}</strong><small>{String(row.state.status ?? "waiting")}</small></div>
      <button type="button" className="button button-secondary button-compact" disabled={busy} onClick={() => void run("join", row.id)}>{en ? "Generate hand-off instructions" : "生成接入说明"}</button>
    </div>)}
    {joined?.bootstrap ? <div className="field field-wide">
      <p className="field-help">{en ? "Review these instructions before pasting them into your trusted Agent. It needs access to local task files and process tools. Your Agent may consume its subscription or API quota. Results still pass the core validator and lease fences." : "请先审阅，再把说明粘贴给你信任的 Agent。它需要读取本机任务文件及执行工具命令，可能消耗其订阅或 API 额度；结果仍须通过上游校验与租约检查。"}</p>
      <textarea rows={8} readOnly value={joined.bootstrap} aria-label={en ? "Agent hand-off instructions" : "Agent 接入说明"} />
      <button type="button" className="button button-secondary button-compact" onClick={() => void navigator.clipboard.writeText(joined.bootstrap!).then(() => setNotice(en ? "Copied. No Agent has been started." : "已复制，未启动任何 Agent。")).catch((error) => setNotice(String(error)))}><Copy size={14} />{en ? "Copy instructions" : "复制接入说明"}</button>
    </div> : null}
    {notice ? <p role="status" className="field-help">{notice}</p> : null}
  </details>;
}
