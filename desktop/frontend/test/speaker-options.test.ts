import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { SpeakerSettings } from "../components/SpeakerSettings";
import { initialState } from "../lib/state";
import { preferredTaskOutput, taskOutputEntries } from "../lib/subtitleOutputs";

test("speaker options are opt-in and disclose downloads, limits and model calls", () => {
  const request = initialState.task.request;
  const off = renderToStaticMarkup(createElement(SpeakerSettings, { request, onChange() {} }));
  assert.match(off, /说话人分离/);
  assert.doesNotMatch(off, /约 450 MB/);
  const on = renderToStaticMarkup(createElement(SpeakerSettings, { request: { ...request, diarize: "judge-audio", stage: "final-srt" }, onChange() {} }));
  assert.match(on, /450 MB/);
  assert.match(on, /增加模型调用/);
  assert.match(on, /仅限非商业|仅非商业/);
  assert.match(on, /FINESUB_DIARIZATION_ARTIFACTS/);
  assert.match(on, /人数上限/);
});

test("speaker files are visible but never replace the ordinary preferred subtitle", () => {
  const outputs = { rawSrt: "clip.srt", "speaker:s1.srt": "clip-s1.srt", "speaker:all.ass": "clip-all.ass", speakerTimeline: "clip-diar.json" };
  assert.equal(preferredTaskOutput(outputs), "clip.srt");
  assert.equal(taskOutputEntries(outputs).length, 4);
});
