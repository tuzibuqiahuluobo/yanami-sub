import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { ProgrammeReferenceSettings } from "../components/ProgrammeReference";
import { ProgrammeRoleExport } from "../components/ProgrammeRoleExport";
import { initialState, reduceAppState } from "../lib/state";
import { preferredTaskOutput, taskOutputEntries } from "../lib/subtitleOutputs";

test("programme reference explains preview, matching and what goes to the model", () => {
  const html = renderToStaticMarkup(createElement(ProgrammeReferenceSettings, {
    inputPath: "C:/clips/host.mp4",
    onChange() {},
  }));
  for (const label of ["选择节目切片", "选择对应 SRT", "预览对齐", "暂停、回放或跳播",
    "只在本机", "字幕文字会发给本次纠错翻译使用的模型"]) {
    assert.ok(html.includes(label), label);
  }
  assert.doesNotMatch(html, /用于本次翻译/);
});

test("role export explains review without changing the preferred subtitle", () => {
  const html = renderToStaticMarkup(createElement(ProgrammeRoleExport, { taskId: "task" }));
  assert.match(html, /重叠、低置信度和没有分组/);
  assert.match(html, /完整字幕不变/);
  const outputs = { finalSrt: "full.srt", programmeReference: "reference.srt",
    "speaker:speaker10.srt": "speaker10.srt", "speaker:speaker2.srt": "speaker2.srt" };
  assert.equal(preferredTaskOutput(outputs), "full.srt");
  assert.deepEqual(taskOutputEntries(outputs).filter(([key]) => key.startsWith("speaker:")).map(([, path]) => path),
    ["speaker2.srt", "speaker10.srt"]);
});

test("selecting a different video clears the previous reference", () => {
  const state = { ...initialState, task: { ...initialState.task, request: {
    ...initialState.task.request, programme_reference: {
      clip: "clip.mp4", subtitle: "clip.srt", subtitle_offset_ms: 0,
      spans: [{ clip_ms: 0, reaction_ms: 1000, length_ms: 2000 }],
    },
  } } };
  const next = reduceAppState(state, { type: "fileSelected", path: "different.mp4" });
  assert.equal(next.task.request.programme_reference, null);
});
