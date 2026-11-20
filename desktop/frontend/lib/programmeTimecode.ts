export type TimecodeParts = [string, string, string, string];
// Unedited historical values keep their original millisecond precision.
export type Timecode = number | TimecodeParts;

export function timecodeParts(ms: number, fps: number | null): TimecodeParts {
  const seconds = Math.floor(ms / 1000);
  const frames = fps ? Math.min(Math.ceil(fps) - 1, Math.round((ms % 1000) * fps / 1000)) : 0;
  const pad = (value: number) => String(value).padStart(2, "0");
  return [pad(Math.floor(seconds / 3600)), pad(Math.floor(seconds / 60) % 60), pad(seconds % 60), pad(frames)];
}

export function timecodeMilliseconds(value: Timecode, fps: number | null): number | null {
  if (typeof value === "number") return value;
  if (value.some(part => !/^\d{0,3}$/.test(part))) return null;
  const [hours, minutes, seconds, frames] = value.map(Number);
  if (hours > 23 || minutes > 59 || seconds > 59 || (frames > 0 && (!fps || frames >= Math.ceil(fps)))) {
    return null;
  }
  const ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + (fps ? Math.round(frames * 1000 / fps) : 0);
  return ms < 86_400_000 ? ms : null;
}
