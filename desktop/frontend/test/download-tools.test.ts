import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { formatChoices } from "../components/LinkDownloadOptions";
import { SubtitleTools } from "../components/SubtitleTools";
import { initialState, reduceAppState } from "../lib/state";
import type { LinkVideoFormat } from "../lib/types";

test("resolution and fps choices come from compatible formats, not a cross product", () => {
  const formats: LinkVideoFormat[] = [
    { format_id: "one", container: "mp4", height: 720, fps: 60 },
    { format_id: "two", container: "mp4", height: 720, fps: 30 },
    { format_id: "three", container: "mp4", height: 480, fps: 30 },
    { format_id: "four", container: "webm", height: 1080, fps: 60 },
  ];
  const defaultChoices = formatChoices(formats);
  assert.deepEqual(defaultChoices.heights, [720, 480]);
  assert.deepEqual(defaultChoices.frameRates, [60, 30]);
  const webm = formatChoices(formats, formats[3]);
  assert.deepEqual(webm.heights, [1080]);
  assert.deepEqual(webm.frameRates, [60]);
});

test("choosing a new file does not carry the previous URL's format", () => {
  const state = { ...initialState, task: { ...initialState.task, request: {
    ...initialState.task.request, link_format: { format_id: "398", container: "mp4" as const },
  } } };
  assert.equal(reduceAppState(state, { type: "fileSelected", path: "new.mp4" }).task.request.link_format, null);
});

test("subtitle tool explains it does not need a video download or model", () => {
  const html = renderToStaticMarkup(createElement(SubtitleTools, { onOpenResources() {} }));
  assert.match(html, /YouTube 字幕下载/);
  assert.match(html, /不下载视频、不调用模型/);
});
