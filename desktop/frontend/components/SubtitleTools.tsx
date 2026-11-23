"use client";

import { useState } from "react";
import { Captions, Download, Search } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { LinkMedia } from "@/lib/types";
import { CustomSelect } from "./CustomSelect";
import { useLanguage } from "./LanguageProvider";

export function SubtitleTools({ onOpenResources }: { onOpenResources: () => void }) {
  const zh = useLanguage().language === "zh";
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<LinkMedia>();
  const [track, setTrack] = useState("0");
  const [extension, setExtension] = useState("srt");
  const [busy, setBusy] = useState<"inspect" | "save">();
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const selected = result?.tracks[Number(track)];
  async function inspect() {
    setBusy("inspect"); setResult(undefined); setError(""); setSaved("");
    try { setResult(await desktopApi.inspectLinkMedia(url.trim(), true)); setTrack("0"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(undefined); }
  }
  async function save() {
    if (!selected) return;
    setBusy("save"); setError(""); setSaved("");
    try { setSaved((await desktopApi.saveLinkSubtitle(url.trim(), selected, extension, result?.title)).path ?? ""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(undefined); }
  }
  return <div className="page page-subtitle-tools">
    <header className="page-header"><div>
      <h1>{zh ? "工具" : "Tools"}</h1>
      <p>{zh ? "下载视频已有的字幕，不必新建字幕任务。" : "Download existing captions without starting a subtitle task."}</p>
    </div></header>
    <section className="primary-panel" aria-label={zh ? "字幕下载" : "Subtitle download"}>
      <div className="section-heading"><h2><Captions size={19} aria-hidden="true" /> {zh ? "YouTube 字幕下载" : "YouTube subtitle download"}</h2></div>
      <form className="subtitle-tool-form" onSubmit={event => { event.preventDefault(); void inspect(); }}>
        <label className="field"><span>{zh ? "视频链接" : "Video link"}</span>
          <input type="url" autoComplete="off" placeholder="https://www.youtube.com/watch?v=…" value={url} disabled={!!busy}
            onChange={event => { setUrl(event.target.value); setResult(undefined); setError(""); setSaved(""); }} /></label>
        <button className="button button-primary" disabled={!!busy || !url.trim()}><Search size={16} aria-hidden="true" />
          {busy === "inspect" ? (zh ? "正在读取…" : "Reading…") : (zh ? "读取字幕" : "List subtitles")}</button>
      </form>
      <p className="field-help">{zh ? "使用本机 yt-dlp。只下载所选字幕，不下载视频、不调用模型。" : "Uses local yt-dlp. Downloads the selected subtitle only, without video or model calls."}</p>
      {result && (result.tracks.length ? <div className="subtitle-tool-results">
        <h3>{result.title || (zh ? "可下载的字幕" : "Available subtitles")}</h3>
        <div className="field-grid">
          <div className="field"><span>{zh ? "字幕轨道" : "Caption track"}</span>
            <CustomSelect ariaLabel={zh ? "字幕轨道" : "Caption track"} disabled={!!busy} value={track} onChange={setTrack}
              options={result.tracks.map((row, index) => ({ value: String(index), label: `${row.label} (${row.language}) · ${row.automatic ? (zh ? "自动生成" : "Automatic") : (zh ? "原有字幕" : "Original")}` }))} /></div>
          <div className="field"><span>{zh ? "保存格式" : "Save as"}</span>
            <CustomSelect ariaLabel={zh ? "保存格式" : "Save as"} disabled={!!busy} value={extension} onChange={setExtension}
              options={["srt", "vtt", "txt"].map(value => ({ value, label: value.toUpperCase() }))} /></div>
        </div>
        <button type="button" className="button button-primary" disabled={!!busy || !selected} onClick={() => void save()}>
          <Download size={16} aria-hidden="true" />{busy === "save" ? (zh ? "正在保存…" : "Saving…") : (zh ? "另存字幕" : "Save subtitle")}</button>
      </div> : <p className="inline-note" role="status">{zh ? "这个视频没有找到可下载的字幕轨道。" : "No downloadable subtitle tracks were found."}</p>)}
      {error ? <div className="error-banner" role="alert"><span>{error}</span><button type="button" className="text-button" onClick={onOpenResources}>{zh ? "检查资源" : "Check resources"}</button></div> : null}
      {saved ? <p className="inline-note" role="status">{zh ? "已保存：" : "Saved: "}{saved}</p> : null}
    </section>
  </div>;
}
