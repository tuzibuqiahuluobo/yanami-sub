import assert from "node:assert/strict";
import test from "node:test";
import { batchRowForSubmit, sharedBatchSettings } from "../lib/batchItemSettings";
import { initialState, reduceAppState } from "../lib/state";
import type { BatchItemRequest } from "../lib/types";

const row: BatchItemRequest = {
  ...initialState.task.request, input: "https://example.test/video?v=AbC", name: "Episode 1",
  stage: "final-srt", group: "", priority: 0, output: "batch/one.srt",
  refined_srt: "first.srt", llm_video: "first.mp4", download_video_source: true,
  link_format: { format_id: "399", container: "mp4" },
};

test("batch shared settings never carry per-item materials or destinations", () => {
  assert.deepEqual(sharedBatchSettings({ name: row.name, output: row.output, refined_srt: row.refined_srt,
    llm_video: row.llm_video, link_format: row.link_format, programme_reference: null, stage: row.stage }),
  { stage: "final-srt" });
});

test("submit preserves the selected item's format but drops incompatible hidden fields", () => {
  const exact = batchRowForSubmit(row);
  assert.deepEqual(exact.link_format, row.link_format);
  assert.equal(exact.name, row.name);
  assert.equal(exact.output, null);
  const raw = batchRowForSubmit({ ...row, stage: "raw-srt", download_video_source: false });
  assert.equal(raw.refined_srt, null);
  assert.equal(raw.llm_video, null);
  assert.equal(raw.link_format, null);
});

test("preparing one batch item keeps its own settings and recognition directory", () => {
  const state = reduceAppState(initialState, { type: "reuseBatchAsr", request: { ...row, resume: true } });
  assert.equal(state.route, "new-task");
  assert.equal(state.task.selectedFile, row.input);
  assert.equal(state.task.request.output, row.output);
  assert.deepEqual(state.task.request.link_format, row.link_format);
  assert.equal(state.task.request.refined_srt, row.refined_srt);
});
