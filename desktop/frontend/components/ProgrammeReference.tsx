"use client";

import { useState } from "react";
import { desktopApi } from "@/lib/bridge";
import type { ProgrammeReference, ProgrammeReferencePreview } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

const blank = (): ProgrammeReference => ({ clip: "", subtitle: "", subtitle_offset_ms: 0,
  spans: [{ clip_ms: 0, reaction_ms: 0, length_ms: 10000 }] });

function time(ms: number) {
  const sec = Math.floor(ms / 1000);
  return [Math.floor(sec / 3600), Math.floor(sec / 60) % 60, sec % 60]
    .map(n => String(n).padStart(2, "0")).join(":") + "." + String(ms % 1000).padStart(3, "0");
}

export function ProgrammeReferenceSettings({ inputPath, value, onChange, disabled, reuse }: {
  inputPath: string;
  value?: ProgrammeReference | null;
  onChange: (value: ProgrammeReference | null) => void;
  disabled?: boolean;
  reuse?: boolean;
}) {
  const { language } = useLanguage();
  const zh = language === "zh";
  const [draft, setDraft] = useState(value ?? blank);
  const [preview, setPreview] = useState<ProgrammeReferencePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function update(next: ProgrammeReference) {
    setDraft(next);
    setPreview(null);
    setError("");
    if (value) onChange(null);
  }
  async function pick(key: "clip" | "subtitle") {
    setBusy(true); setError("");
    try {
      const result = await (key === "clip" ? desktopApi.selectInputFile() : desktopApi.selectSubtitleFile());
      if (result.path) update({ ...draft, [key]: result.path });
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  async function check() {
    setBusy(true); setError(""); setPreview(null);
    try { setPreview(await desktopApi.previewProgrammeReference(inputPath, draft)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  const locked = disabled || busy || reuse;
  return <details className="programme-reference field-wide">
    <summary>{zh ? "节目参考字幕（可选）" : "Programme reference subtitles (optional)"}{value ? (zh ? " · 已启用" : " · enabled") : ""}</summary>
    <p className="field-help">{zh ? "适合主播看前瞻、PV 等视频。切片只在本机检查时长；对齐后，相关字幕文字会发给本次纠错翻译使用的模型，协助译名与语境，不替换或删除主播发言。" : "For reactions to previews, trailers and other clips. The clip is only checked locally. Aligned subtitle text goes to the correction model for context and terminology, not to replace or remove the host's speech."}</p>
    {reuse ? <p role="status">{zh ? "节目参考需要新建输出，请先取消复用旧任务。" : "Programme reference needs a new output. Turn off reuse first."}</p> : null}
    <div className="programme-reference-tools">
      <button type="button" className="button button-secondary" disabled={locked} onClick={() => void pick("clip")}>{zh ? "选择节目切片" : "Choose programme clip"}</button>
      <span title={draft.clip}>{draft.clip.split(/[\\/]/).pop() || (zh ? "未选择视频" : "No video selected")}</span>
      <button type="button" className="button button-secondary" disabled={locked} onClick={() => void pick("subtitle")}>{zh ? "选择对应 SRT" : "Choose matching SRT"}</button>
      <span title={draft.subtitle}>{draft.subtitle.split(/[\\/]/).pop() || (zh ? "未选择字幕" : "No subtitles selected")}</span>
    </div>
    <label className="field"><span>{zh ? "切片在整场 SRT 中的起点（秒）" : "Clip start in the full-programme SRT (seconds)"}</span>
      <input type="number" min="0" max="86399.999" step="0.001" disabled={locked} value={draft.subtitle_offset_ms / 1000}
        onChange={e => update({ ...draft, subtitle_offset_ms: Math.round(Number(e.target.value) * 1000) })} />
      <small className="field-help">{zh ? "SRT 已从切片开头计时就留 0；例如切片从前瞻第 10 分钟开始，字幕仍是整场时间，则填 600。" : "Leave 0 for clip-relative SRT. Enter 600 if the clip begins ten minutes into the source and the SRT uses full-programme time."}</small>
    </label>
    <p className="field-help">{zh ? "在两个播放器找到同一画面，填下各自时间，再填接下来连续播放的秒数。暂停、回放或跳播后另加一段，勿跨过断点。" : "Find the same frame in both players. Enter each time and the continuous duration that follows. Add a range after a pause, replay or seek."}</p>
    {draft.spans.map((span, index) => <fieldset key={index} className="programme-span" disabled={locked}>
      <legend>{zh ? `区间 ${index + 1}` : `Range ${index + 1}`}</legend>
      <div className="programme-time-grid">{([
        ["clip_ms", zh ? "切片位置（秒）" : "Clip time (s)"],
        ["reaction_ms", zh ? "主播视频位置（秒）" : "Reaction time (s)"],
        ["length_ms", zh ? "连续播放（秒）" : "Continuous duration (s)"],
      ] as const).map(([key, label]) => <label className="field" key={key}><span>{label}</span>
        <input type="number" min={key === "length_ms" ? 0.001 : 0} max="86399.999" step="0.001" value={span[key] / 1000}
          onChange={e => update({ ...draft, spans: draft.spans.map((row, i) => i === index
            ? { ...row, [key]: Math.round(Number(e.target.value) * 1000) } : row) })} /></label>)}</div>
      {draft.spans.length > 1 ? <button type="button" className="button button-secondary" onClick={() => update({ ...draft, spans: draft.spans.filter((_, i) => index !== i) })}>{zh ? "移除此段" : "Remove range"}</button> : null}
    </fieldset>)}
    <div className="programme-reference-actions">
      <button type="button" className="button button-secondary" disabled={locked || draft.spans.length >= 30} onClick={() => update({ ...draft, spans: [...draft.spans, blank().spans[0]] })}>{zh ? "添加对齐区间" : "Add range"}</button>
      <button type="button" className="button button-secondary" disabled={locked || !draft.clip || !draft.subtitle} onClick={() => void check()}>{busy ? (zh ? "读取中…" : "Reading…") : (zh ? "预览对齐" : "Preview alignment")}</button>
      {value ? <button type="button" className="button button-secondary" disabled={locked} onClick={() => onChange(null)}>{zh ? "停用参考" : "Disable reference"}</button> : null}
    </div>
    {error ? <p className="api-key-error" role="alert">{error}</p> : null}
    {preview ? <div className="programme-reference-preview" role="status">
      <strong>{zh ? `对齐到 ${preview.count} 条 · 切片时长 ${time(preview.duration_ms)}` : `${preview.count} aligned cues · clip duration ${time(preview.duration_ms)}`}</strong>
      <p className="field-help">{zh ? "下方为主播视频时间，核对开头及中途没有错位后再启用。" : "Times below are on the reaction timeline. Check that the start and later frames line up before enabling."}</p>
      <ol>{preview.sample.map((cue, index) => <li key={index}><code>{time(cue.start_ms)} – {time(cue.end_ms)}</code><span>{cue.text}</span></li>)}</ol>
      <button type="button" className="button button-primary" disabled={locked || Boolean(value)} onClick={() => onChange(draft)}>{value ? (zh ? "已启用" : "Enabled") : (zh ? "用于本次翻译" : "Use for this translation")}</button>
    </div> : null}
  </details>;
}
