"use client";
import { useState } from "react";
import { saveUi } from "@/lib/preferences";
import { playNotification, soundSettings, type SoundSettings as SoundPreferences } from "@/lib/notificationSound";
import { useLanguage } from "./LanguageProvider";

export function SoundSettings() {
  const { language } = useLanguage();
  const en = language === "en";
  const [value, setValue] = useState(soundSettings);
  const [error, setError] = useState("");
  const update = (patch: Partial<SoundPreferences>) => {
    const next = { ...value, ...patch };
    setValue(next);
    saveUi({ sound: next });
  };
  return <fieldset className="sound-settings">
    <legend>{en ? "Notification sound" : "提示音"}</legend>
    <p className="field-help">{en ? "Built-in: you ピロリン · Default volume 50%. App volume only." : "内置：you ピロリン · 默认音量 50%，仅调整本应用音量。"}</p>
    <label className="switch-row"><input type="checkbox" checked={value.enabled} onChange={(event) => update({ enabled: event.target.checked })} /><span>{en ? "Enable sounds" : "启用提示音"}</span></label>
    <div className="sound-events">{(["task", "batch", "download"] as const).map((key) => <label key={key} className="switch-row"><input type="checkbox" checked={value[key]} onChange={(event) => update({ [key]: event.target.checked })} /><span>{en ? { task: "Task complete", batch: "Batch complete", download: "Download ready" }[key] : { task: "任务完成", batch: "批处理完成", download: "下载就绪" }[key]}</span></label>)}</div>
    <label className="field"><span>{en ? "Volume" : "音量"} · {value.volume}%</span><input aria-label={en ? "Sound volume" : "提示音音量"} type="range" min="0" max="100" value={value.volume} onChange={(event) => update({ volume: Number(event.target.value) })} /></label>
    <button type="button" className="button button-secondary button-compact" onClick={async () => setError(await playNotification("task", true) ? "" : en ? "No sound played. Check volume, audio device or playback permission." : "未能播放，请检查音量、音频设备或播放权限。")}>{en ? "Test sound" : "试听音效"}</button>
    {error ? <p role="status" className="field-help">{error}</p> : null}
  </fieldset>;
}
