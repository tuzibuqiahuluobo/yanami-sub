"use client";

import { useEffect, useId, useState } from "react";
import { desktopApi } from "@/lib/bridge";
import { timecodeMilliseconds, timecodeParts, type Timecode, type TimecodeParts } from "@/lib/programmeTimecode";
import type { ProgrammeReference, ProgrammeReferencePreview } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

const blankSpan = () => ({ clip_ms: 0, reaction_ms: 0, length_ms: 10000 });
type Draft = Omit<ProgrammeReference, "subtitle_offset_ms" | "spans"> & {
  subtitle_offset_ms: Timecode;
  spans: Record<keyof ReturnType<typeof blankSpan>, Timecode>[];
};

function useFrameRate(path: string) {
  const [rate, setRate] = useState<{ path: string; fps: number | null }>();
  useEffect(() => {
    if (!path) return;
    let current = true;
    desktopApi.programmeFrameRate(path)
      .then(({ fps }) => { if (current) setRate({ path, fps }); })
      .catch(() => { if (current) setRate({ path, fps: null }); });
    return () => { current = false; };
  }, [path]);
  return rate?.path === path ? rate.fps : undefined;
}

function time(ms: number) {
  const sec = Math.floor(ms / 1000);
  return [Math.floor(sec / 3600), Math.floor(sec / 60) % 60, sec % 60]
    .map(n => String(n).padStart(2, "0")).join(":") + "." + String(ms % 1000).padStart(3, "0");
}

function TimecodeField({ label, value, fps, disabled, positive, zh, onChange }: {
  label: string;
  value: Timecode;
  fps?: number | null;
  disabled?: boolean;
  positive?: boolean;
  zh: boolean;
  onChange: (value: TimecodeParts) => void;
}) {
  const id = useId();
  const parts = typeof value === "number" ? timecodeParts(value, fps ?? null) : value;
  const ms = timecodeMilliseconds(value, fps ?? null);
  const invalid = ms === null || (positive && ms === 0);
  const units = zh ? ["时", "分", "秒", "帧"] : ["Hours", "Min", "Sec", "Frames"];
  const partLimits = [23, 59, 59, fps ? Math.ceil(fps) - 1 : 0];
  const rangeError = zh ? `时 0–23，分秒 0–59，帧 0–${partLimits[3]}` : `Hours 0–23, min/sec 0–59, frames 0–${partLimits[3]}.`;
  const error = !fps && Number(parts[3]) > 0
    ? (zh ? "未读到帧率，帧请留 0" : "No frame rate detected. Leave frames at 0.")
    : rangeError;
  return <div className="programme-timecode field" role="group" aria-labelledby={`${id}-label`}>
    <span id={`${id}-label`}>{label}</span>
    <div className="programme-timecode-parts">
      {units.map((unit, index) => <label key={unit} className="field">
        <span>{unit}</span>
        <input type="text" inputMode="numeric" maxLength={index === 3 ? 3 : 2}
          value={parts[index]} disabled={disabled} aria-invalid={Number(parts[index]) > partLimits[index] || undefined}
          aria-label={`${label} · ${unit}`} aria-describedby={`${id}-value`}
          onChange={e => {
            if (!/^\d*$/.test(e.target.value)) return;
            const next: TimecodeParts = [...parts];
            next[index] = e.target.value;
            onChange(next);
          }}
          onPaste={e => {
            const text = e.clipboardData.getData("text").trim();
            if (!/[:：;；]/.test(text)) return;
            e.preventDefault();
            const pasted = text.match(/^(\d{1,2})[:：](\d{1,2})[:：](\d{1,2})(?:[:：](\d{1,3}))?$/);
            if (pasted) onChange([pasted[1], pasted[2], pasted[3], pasted[4] ?? "00"]);
          }} />
      </label>)}
    </div>
    <small className={invalid ? "api-key-error" : "field-help"} id={`${id}-value`}>
      {ms === null
        ? error
        : invalid ? (zh ? "连续播放时长必须大于 0" : "Duration must be greater than zero.")
        : <code>{time(ms)}</code>}
    </small>
  </div>;
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
  const [draft, setDraft] = useState<Draft>(value ?? { clip: "", subtitle: "", subtitle_offset_ms: 0, spans: [blankSpan()] });
  const [opened, setOpened] = useState(false);
  const [preview, setPreview] = useState<ProgrammeReferencePreview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const clipFps = useFrameRate(opened ? draft.clip : "");
  const reactionFps = useFrameRate(opened ? inputPath : "");
  const offset = timecodeMilliseconds(draft.subtitle_offset_ms, clipFps ?? null);
  const spans = draft.spans.map(span => ({
    clip_ms: timecodeMilliseconds(span.clip_ms, clipFps ?? null),
    reaction_ms: timecodeMilliseconds(span.reaction_ms, reactionFps ?? null),
    length_ms: timecodeMilliseconds(span.length_ms, clipFps ?? null),
  }));
  const converted = spans.flatMap(({ clip_ms, reaction_ms, length_ms }) =>
    clip_ms === null || reaction_ms === null || length_ms === null || length_ms <= 0
      ? [] : [{ clip_ms, reaction_ms, length_ms }]);
  const alignment: ProgrammeReference | null = offset !== null && converted.length === spans.length
    ? { clip: draft.clip, subtitle: draft.subtitle, subtitle_offset_ms: offset, spans: converted }
    : null;

  function update(next: Draft) {
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
    if (!alignment) return;
    setBusy(true); setError(""); setPreview(null);
    try { setPreview(await desktopApi.previewProgrammeReference(inputPath, alignment)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  const locked = disabled || busy || reuse;
  function rateText(fps: number | null | undefined, path: string) {
    if (!path) return zh ? "选视频后读取" : "Select video";
    if (fps === undefined) return zh ? "读取中…" : "Reading…";
    return fps ? `${Number(fps.toFixed(3))} fps` : zh ? "未读到，帧留 0" : "Not detected; leave frames at 0";
  }
  return <details className="programme-reference field-wide" onToggle={e => { if (e.currentTarget.open) setOpened(true); }}>
    <summary>{zh ? "节目参考字幕（可选）" : "Programme reference subtitles (optional)"}{value ? (zh ? " · 已启用" : " · enabled") : ""}</summary>
    <p className="field-help">{zh ? "适合主播看前瞻、PV 等视频。切片只在本机检查时长；对齐后，相关字幕文字会发给本次纠错翻译使用的模型，协助译名与语境，不替换或删除主播发言。" : "For reactions to previews, trailers and other clips. The clip is only checked locally. Aligned subtitle text goes to the correction model for context and terminology, not to replace or remove the host's speech."}</p>
    {reuse ? <p role="status">{zh ? "节目参考需要新建输出，请先取消复用旧任务。" : "Programme reference needs a new output. Turn off reuse first."}</p> : null}
    <div className="programme-reference-tools">
      <button type="button" className="button button-secondary" disabled={locked} onClick={() => void pick("clip")}>{zh ? "选择节目切片" : "Choose programme clip"}</button>
      <span title={draft.clip}>{draft.clip.split(/[\\/]/).pop() || (zh ? "未选择视频" : "No video selected")}</span>
      <button type="button" className="button button-secondary" disabled={locked} onClick={() => void pick("subtitle")}>{zh ? "选择对应 SRT" : "Choose matching SRT"}</button>
      <span title={draft.subtitle}>{draft.subtitle.split(/[\\/]/).pop() || (zh ? "未选择字幕" : "No subtitles selected")}</span>
    </div>
    <p className="field-help" role="status">{zh ? "切片帧率" : "Clip frame rate"}：{rateText(clipFps, draft.clip)} · {zh ? "主播视频帧率" : "Reaction frame rate"}：{rateText(reactionFps, inputPath)}</p>
    <p className="field-help">{zh ? "按播放器经过时间填时、分、秒、帧（可粘贴 00:01:23:12）。不按丢帧时间码计数；可变帧率按平均帧率近似，请核对预览。" : "Use elapsed playback time in hours, minutes, seconds and frames (you can paste 00:01:23:12). Drop-frame timecode is not supported; variable rates use an average. Check the preview."}</p>
    <TimecodeField label={zh ? "切片在整场 SRT 中的起点" : "Clip start in full-programme SRT"}
      value={draft.subtitle_offset_ms} fps={clipFps} disabled={locked} zh={zh}
      onChange={v => update({ ...draft, subtitle_offset_ms: v })} />
    <p className="field-help">{zh ? "SRT 从切片开头计时就全留 0；整场字幕从第 10 分钟切入，就在「分」填 10。「起点」与「连续播放时长」的帧均按切片帧率计算。" : "Leave zero for clip-relative SRT. For a cut ten minutes into the programme enter 10 in Min. Offset and duration frames use the clip rate."}</p>
    <p className="field-help">{zh ? "在两个播放器找到同一画面，填下各自时间和接下来连续播放的时长。暂停、回放或跳播后另加一段，勿跨过断点。" : "Find the same frame in both players. Enter each time and the continuous duration that follows. Add a range after a pause, replay or seek."}</p>
    {draft.spans.map((span, index) => <fieldset key={index} className="programme-span" disabled={locked}>
      <legend>{zh ? `区间 ${index + 1}` : `Range ${index + 1}`}</legend>
      <div className="programme-time-grid">{([
        ["clip_ms", zh ? "切片位置" : "Clip time", clipFps],
        ["reaction_ms", zh ? "主播视频位置" : "Reaction time", reactionFps],
        ["length_ms", zh ? "连续播放时长" : "Continuous duration", clipFps],
      ] as const).map(([key, label, fps]) => <TimecodeField key={key} label={label} value={span[key]} fps={fps}
        disabled={locked} positive={key === "length_ms"} zh={zh}
        onChange={v => update({ ...draft, spans: draft.spans.map((row, i) => i === index
          ? { ...row, [key]: v } : row) })} />)}</div>
      {draft.spans.length > 1 ? <button type="button" className="button button-secondary" onClick={() => update({ ...draft, spans: draft.spans.filter((_, i) => index !== i) })}>{zh ? "移除此段" : "Remove range"}</button> : null}
    </fieldset>)}
    <div className="programme-reference-actions">
      <button type="button" className="button button-secondary" disabled={locked || draft.spans.length >= 30} onClick={() => update({ ...draft, spans: [...draft.spans, blankSpan()] })}>{zh ? "添加对齐区间" : "Add range"}</button>
      <button type="button" className="button button-secondary" disabled={locked || !alignment || !draft.clip || !draft.subtitle} onClick={() => void check()}>{busy ? (zh ? "读取中…" : "Reading…") : (zh ? "预览对齐" : "Preview alignment")}</button>
      {value ? <button type="button" className="button button-secondary" disabled={locked} onClick={() => onChange(null)}>{zh ? "停用参考" : "Disable reference"}</button> : null}
    </div>
    {error ? <p className="api-key-error" role="alert">{error}</p> : null}
    {preview ? <div className="programme-reference-preview" role="status">
      <strong>{zh ? `对齐到 ${preview.count} 条 · 切片时长 ${time(preview.duration_ms)}` : `${preview.count} aligned cues · clip duration ${time(preview.duration_ms)}`}</strong>
      <p className="field-help">{zh ? "下方为主播视频时间，核对开头及中途没有错位后再启用。" : "Times below are on the reaction timeline. Check that the start and later frames line up before enabling."}</p>
      <ol>{preview.sample.map((cue, index) => <li key={index}><code>{time(cue.start_ms)} – {time(cue.end_ms)}</code><span>{cue.text}</span></li>)}</ol>
      <button type="button" className="button button-primary" disabled={locked || !alignment || Boolean(value)} onClick={() => { if (alignment) onChange(alignment); }}>{value ? (zh ? "已启用" : "Enabled") : (zh ? "用于本次翻译" : "Use for this translation")}</button>
    </div> : null}
  </details>;
}
