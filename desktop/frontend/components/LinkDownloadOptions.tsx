"use client";

import { useEffect, useState } from "react";
import { Film, RotateCcw } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { LinkFormat, LinkVideoFormat } from "@/lib/types";
import { CustomSelect } from "./CustomSelect";
import { useLanguage } from "./LanguageProvider";

export function formatChoices(formats: LinkVideoFormat[], choice?: LinkFormat | null) {
  const current = formats.find(row => row.format_id === choice?.format_id && row.container === choice.container)
    ?? formats.find(row => row.container === "mp4" && row.height <= 720) ?? formats[0];
  const containers = [...new Set(formats.map(row => row.container))];
  const containerRows = formats.filter(row => row.container === current?.container);
  const heights = [...new Set(containerRows.map(row => row.height))];
  const heightRows = containerRows.filter(row => row.height === current?.height);
  const frameRates = [...new Set(heightRows.flatMap(row => row.fps === null ? [] : [row.fps]))];
  return { current, containers, containerRows, heights, heightRows, frameRates };
}

export function LinkDownloadOptions({ url, choice, locked, onSelect }: {
  url: string;
  choice?: LinkFormat | null;
  locked?: boolean;
  onSelect: (choice: LinkFormat | null) => void;
}) {
  const zh = useLanguage().language === "zh";
  const [formats, setFormats] = useState<LinkVideoFormat[]>();
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (locked) return;
    let active = true;
    desktopApi.inspectLinkMedia(url)
      .then(data => { if (active) setFormats(data.formats); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [url, attempt, locked]);

  if (locked) return null;
  const resetFormat = choice ? <button type="button" className="button button-secondary button-compact" onClick={() => onSelect(null)}>
    <RotateCcw size={14} aria-hidden="true" />{zh ? "恢复自动" : "Use automatic"}
  </button> : null;
  if (failed) return <div className="link-format-status field-help" role="status">
    {zh ? "暂时无法读取视频档位。" : "Could not read video formats."}
    <button type="button" className="button button-secondary button-compact" onClick={() => { setFailed(false); setFormats(undefined); setAttempt(x => x + 1); }}>{zh ? "重试" : "Retry"}</button>
    {resetFormat}
  </div>;
  if (!formats) return <p className="link-format-status field-help" role="status">{zh ? "正在读取可下载的视频档位…" : "Checking available video formats…"}</p>;
  const { current, containers, containerRows, heights, heightRows, frameRates } = formatChoices(formats, choice);
  const stale = choice && !formats.some(row => row.format_id === choice.format_id && row.container === choice.container);
  if (!choice && (!current || Math.max(containers.length, heights.length, frameRates.length) < 2)) return null;
  const select = (row: LinkVideoFormat | undefined) => {
    if (row) onSelect({ container: row.container, format_id: row.format_id });
  };
  return <section className="link-download-options" aria-label={zh ? "链接下载选项" : "Link download options"}>
    <div className="link-format-heading">
      <span><Film size={16} aria-hidden="true" /> {zh ? "下载档位" : "Download quality"}</span>
      {resetFormat ?? <span className="field-help">{zh ? "自动 · 调整任一项后使用所选档位" : "Automatic · Change a field to use that format"}</span>}
    </div>
    {stale ? <p className="field-help" role="status">{zh ? "上次选择的档位已不可用，请重新选择或恢复自动。" : "The previous format is no longer available. Select again or use automatic."}</p> : null}
    <div className="field-grid">
      {containers.length > 1 && <div className="field"><span>{zh ? "视频格式" : "Container"}</span>
        <CustomSelect ariaLabel={zh ? "视频格式" : "Container"} value={current?.container ?? ""}
          options={containers.map(value => ({ value, label: value.toUpperCase() }))}
          onChange={value => select(formats.find(row => row.container === value && row.height === current?.height && row.fps === current?.fps)
            ?? formats.find(row => row.container === value && row.height === current?.height)
            ?? formats.find(row => row.container === value))} /></div>}
      {heights.length > 1 && <div className="field"><span>{zh ? "画质" : "Resolution"}</span>
        <CustomSelect ariaLabel={zh ? "画质" : "Resolution"} value={String(current?.height ?? "")}
          options={heights.map(height => ({ value: String(height), label: `${height}p` }))}
          onChange={value => select(containerRows.find(row => row.height === Number(value) && row.fps === current?.fps)
            ?? containerRows.find(row => row.height === Number(value)))} /></div>}
      {frameRates.length > 1 && <div className="field"><span>{zh ? "帧率" : "Frame rate"}</span>
        <CustomSelect ariaLabel={zh ? "帧率" : "Frame rate"} value={String(current?.fps ?? "")}
          options={frameRates.map(fps => ({ value: String(fps), label: `${fps} fps` }))}
          onChange={value => select(heightRows.find(row => row.fps === Number(value)))} /></div>}
    </div>
    {choice && !stale && current ? <small className="field-help">
      {zh ? "已选：" : "Selected: "}{current.container.toUpperCase()} · {current.height}p{current.fps ? ` · ${current.fps} fps` : ""}
    </small> : null}
  </section>;
}
