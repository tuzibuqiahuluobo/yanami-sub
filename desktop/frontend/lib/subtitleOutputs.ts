import type { PipelineStage } from "./types";

const SUBTITLE_OUTPUT_KEYS = [
  "finalSrt",
  "translatedSrt",
  "rawSrt",
] as const;

const TASK_OUTPUT_KEYS = [
  ...SUBTITLE_OUTPUT_KEYS,
  "stableJson",
  "alignedJson",
  "vocalAudio",
  "speakerTimeline",
  "speakerJudge",
  "programmeReference",
] as const;


function orderedOutputEntries(
  keys: readonly string[],
  outputs: Record<string, string> | undefined,
): [string, string][] {
  if (!outputs) return [];
  return keys.flatMap((key) => {
    const path = outputs[key];
    return path ? [[key, path] as [string, string]] : [];
  });
}


export function subtitleOutputEntries(
  outputs: Record<string, string> | undefined,
): [string, string][] {
  return orderedOutputEntries(SUBTITLE_OUTPUT_KEYS, outputs);
}


export function preferredSubtitleOutput(
  outputs: Record<string, string> | undefined,
): string | undefined {
  return subtitleOutputEntries(outputs)[0]?.[1];
}

export function hasRequestedSubtitleOutput(
  stage: PipelineStage,
  outputs: Record<string, string>,
): boolean {
  switch (stage) {
    case "raw-srt": return Boolean(outputs.rawSrt);
    case "translated-srt": return Boolean(outputs.translatedSrt);
    case "final-srt": return Boolean(outputs.finalSrt);
    default: return false;
  }
}


export function taskOutputEntries(
  outputs: Record<string, string> | undefined,
): [string, string][] {
  return [...orderedOutputEntries(TASK_OUTPUT_KEYS, outputs),
    ...Object.entries(outputs ?? {}).filter(([key, path]) => key.startsWith("speaker:") && Boolean(path)).sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))];
}


export function preferredTaskOutput(
  outputs: Record<string, string> | undefined,
): string | undefined {
  return taskOutputEntries(outputs)[0]?.[1];
}
