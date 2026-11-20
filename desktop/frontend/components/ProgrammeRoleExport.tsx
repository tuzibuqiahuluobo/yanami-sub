"use client";

import { useState } from "react";
import { desktopApi } from "@/lib/bridge";
import type { SubtitleRoleResult } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";
import { CustomSelect } from "./CustomSelect";

export function ProgrammeRoleExport({ taskId }: { taskId: string }) {
  const zh = useLanguage().language === "zh";
  const [info, setInfo] = useState<SubtitleRoleResult>();
  const [result, setResult] = useState<SubtitleRoleResult>();
  const [assignment, setAssignment] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  return <details className="speaker-output-group">
    <summary>{zh ? "按主播 / 节目导出译文" : "Export host / programme translations"}</summary>
    <p className="field-help">{zh ? "按字幕样本的时间试听，再为确认无误的轨号分组。重叠、低置信度和没有分组的句子会放进「待确认」。完整字幕不变。" : "Listen at the sample times, then assign only tracks you recognize. Overlap, uncertainty and unassigned cues go to Review. The full subtitle stays unchanged."}</p>
    {!info ? <button type="button" className="button button-secondary" disabled={busy}
      onClick={() => void run(async () => setInfo(await desktopApi.programmeSubtitleRoles(taskId)))}>{zh ? "读取可分组的轨号" : "Load assignable tracks"}</button> : null}
    {info?.tracks?.map(track => <div key={track.track} className="field programme-role-track">
      <span><strong>{track.track}</strong> · {track.count} {zh ? "条" : "cues"} · {track.sample_ms / 1000}s · {track.sample}</span>
      <CustomSelect disabled={busy} ariaLabel={zh ? `为 ${track.track} 分组` : `Group ${track.track}`}
        value={assignment[track.track] || ""} options={[
          { value: "", label: zh ? "待确认" : "Review" },
          { value: "host", label: zh ? "主播" : "Host" },
          { value: "programme", label: zh ? "节目" : "Programme" },
        ]} onChange={role => {
        setResult(undefined);
        const next = { ...assignment };
        if (role) next[track.track] = role;
        else delete next[track.track];
        setAssignment(next);
      }} />
    </div>)}
    {info ? <button type="button" className="button button-primary" disabled={busy || !Object.keys(assignment).length}
      onClick={() => void run(async () => setResult(await desktopApi.programmeSubtitleRoles(taskId, assignment)))}>{zh ? "导出分组字幕" : "Export grouped subtitles"}</button> : null}
    {error ? <p role="alert" className="api-key-error">{error}</p> : null}
    {busy ? <p role="status">{zh ? "正在处理…" : "Working…"}</p> : null}
    {result?.counts ? <div role="status"><p>{zh ? "已导出：" : "Exported: "}{result.directory}</p>
      <p>{zh ? "主播" : "Host"} {result.counts.host} · {zh ? "节目" : "Programme"} {result.counts.programme} · {zh ? "待确认" : "Review"} {result.counts.review}</p>
      <button type="button" className="button button-secondary" onClick={() => void run(async () => { await desktopApi.openTasksDirectory(taskId); })}>{zh ? "打开任务目录" : "Open task folder"}</button></div> : null}
  </details>;
}
