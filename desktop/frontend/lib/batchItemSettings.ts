import type { BatchItemRequest, TaskRequest } from "./types";

const itemKeys = ["name", "output", "llm_video", "refined_srt", "link_format", "programme_reference"] as const;

export function sharedBatchSettings(changes: Partial<Omit<TaskRequest, "input">>) {
  const shared = { ...changes };
  for (const key of itemKeys) delete shared[key];
  return shared;
}

export function batchRowForSubmit(item: BatchItemRequest): BatchItemRequest {
  const translation = item.stage === "translated-srt" || item.stage === "final-srt";
  return {
    ...item, output: null, programme_reference: null,
    llm_video: translation ? item.llm_video : null,
    refined_srt: translation ? item.refined_srt : null,
    link_format: item.download_video_source && /^https?:\/\//i.test(item.input) ? item.link_format : null,
  };
}
