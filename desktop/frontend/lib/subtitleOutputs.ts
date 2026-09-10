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


export function taskOutputEntries(
  outputs: Record<string, string> | undefined,
): [string, string][] {
  return orderedOutputEntries(TASK_OUTPUT_KEYS, outputs);
}


export function preferredTaskOutput(
  outputs: Record<string, string> | undefined,
): string | undefined {
  return taskOutputEntries(outputs)[0]?.[1];
}
