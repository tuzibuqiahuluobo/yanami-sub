"use client";
import { useState, type CSSProperties } from "react";
import { Volume2 } from "lucide-react";
import { saveUi } from "@/lib/preferences";
import { playNotification, soundSettings, type SoundSettings as SoundPreferences } from "@/lib/notificationSound";
import { useLanguage } from "./LanguageProvider";

export function SoundSettings() {
  const { language } = useLanguage();
  const en = language === "en";
  const [value, setValue] = useState(soundSettings);
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);
  const update = (patch: Partial<SoundPreferences>) => {
    const next = { ...value, ...patch };
    setValue(next);
    saveUi({ sound: next });
  };
  return (
    <section className="sound-settings" aria-labelledby="settings-sounds-title">
      <div className="sound-heading">
        <div>
          <h3 id="settings-sounds-title">{en ? "Notification sound" : "提示音"}</h3>
          <p className="field-help">{en ? "Built-in: you ピロリン · Default volume 50%. App volume only." : "内置：you ピロリン · 默认音量 50%，仅调整本应用音量。"}</p>
        </div>
        <SoundToggle label={en ? "Enable sounds" : "启用提示音"} checked={value.enabled} onChange={(enabled) => update({ enabled })} />
      </div>
      <div className="sound-events">
        {(["task", "batch", "download"] as const).map((key) => {
          const label = en ? { task: "Task complete", batch: "Batch complete", download: "Download ready" }[key] : { task: "任务完成", batch: "批处理完成", download: "下载就绪" }[key];
          return (
            <div key={key} className={`sound-event${value.enabled ? "" : " is-disabled"}`}>
              <span>{label}</span>
              <SoundToggle label={label} checked={value[key]} disabled={!value.enabled} onChange={(checked) => update({ [key]: checked })} />
            </div>
          );
        })}
      </div>
      <div className="sound-volume-row">
        <div className="sound-volume-control">
          <div className="sound-volume-label">
            <label htmlFor="notification-volume">{en ? "Volume" : "音量"}</label>
            <output htmlFor="notification-volume">{value.volume}%</output>
          </div>
          <input id="notification-volume" className="sound-range" type="range" min="0" max="100" value={value.volume}
            style={{ "--sound-volume": `${value.volume}%` } as CSSProperties}
            onChange={(event) => update({ volume: Number(event.target.value) })} />
        </div>
        <button type="button" className="button button-secondary button-compact" disabled={testing} aria-busy={testing} onClick={async () => {
          setTesting(true);
          setError("");
          try {
            setError(await playNotification("task", true) ? "" : en ? "No sound played. Check volume, audio device or playback permission." : "未能播放，请检查音量、音频设备或播放权限。");
          } finally {
            setTesting(false);
          }
        }}><Volume2 size={15} aria-hidden="true" />{en ? "Test sound" : "试听音效"}</button>
      </div>
      {error ? <p role="status" className="field-help">{error}</p> : null}
    </section>
  );
}

function SoundToggle({ label, checked, disabled = false, onChange }: {
  label: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void;
}) {
  return (
    <label className="sound-switch">
      <input type="checkbox" role="switch" aria-label={label} checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span className="sound-switch-track" aria-hidden="true" />
    </label>
  );
}
