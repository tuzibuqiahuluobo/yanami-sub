import { uiValue } from "./preferences";

export type SoundEvent = "task" | "batch" | "download";
export interface SoundSettings { enabled: boolean; volume: number; task: boolean; batch: boolean; download: boolean }
export const DEFAULT_SOUND: SoundSettings = { enabled: true, volume: 50, task: true, batch: true, download: true };
export function soundSettings(): SoundSettings {
  const stored = uiValue<Partial<SoundSettings> | null>("sound", {});
  const value = stored && typeof stored === "object" ? stored : {};
  return {
    enabled: typeof value.enabled === "boolean" ? value.enabled : true,
    volume: typeof value.volume === "number" && Number.isFinite(value.volume) ? Math.max(0, Math.min(100, value.volume)) : 50,
    task: typeof value.task === "boolean" ? value.task : true,
    batch: typeof value.batch === "boolean" ? value.batch : true,
    download: typeof value.download === "boolean" ? value.download : true,
  };
}
let audio: HTMLAudioElement | null = null;
let lastPlayed = 0;
export async function playNotification(event: SoundEvent, preview = false): Promise<boolean> {
  const settings = soundSettings();
  if ((!preview && (!settings.enabled || !settings[event])) || settings.volume === 0 || typeof Audio === "undefined") return false;
  // Coalesce simultaneous completions; never overlap the one-second clip.
  if (!preview && Date.now() - lastPlayed < 1200) return false;
  const started = Date.now();
  lastPlayed = started;
  try {
    audio ??= new Audio("./sounds/completion.wav");
    audio.volume = settings.volume / 100;
    audio.pause();
    audio.currentTime = 0;
    await audio.play();
    return true;
  } catch {
    if (lastPlayed === started) lastPlayed = 0;
    return false; // A missing device/autoplay denial must not fail a task.
  }
}
