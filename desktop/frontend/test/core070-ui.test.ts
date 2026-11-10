import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { chromium } from "playwright-core";
import { SpeakerSettings } from "../components/SpeakerSettings";
import { initialState } from "../lib/state";
import { summarizeTaskError } from "../lib/formatters";
import { presetLabel } from "../lib/routingLabels";
import { readStylesheet } from "./stylesheet";

test("speaker controls fit narrow containers and large fonts without overlap", async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage();
    const markup = renderToStaticMarkup(createElement(SpeakerSettings, { request: { ...initialState.task.request, diarize: "acoustics" }, onChange() {} }));
    for (const width of [340, 620, 840]) {
      await page.setViewportSize({ width, height: 900 });
      await page.setContent('<style>' + readStylesheet() + '</style><main style="width:100%;font-size:20px">' + markup + '</main>');
      await page.locator("details").evaluate((node) => { (node as HTMLDetailsElement).open = true; });
      const fields = page.locator(".speaker-model-grid > .field");
      const a = await fields.nth(0).boundingBox();
      const b = await fields.nth(1).boundingBox();
      assert.ok(a && b);
      assert.ok(a.x + a.width <= b.x + 1 || a.y + a.height <= b.y + 1);
    }
  } finally { await browser.close(); }
});

test("preset descriptions and errors explain actions without assuming quota", () => {
  assert.match(presetLabel("agy", "agy", false), /Antigravity/);
  assert.match(presetLabel("fast", "fast", true), /no retrieval/);
  assert.match(summarizeTaskError("Authentication required"), /重新登录/);
  assert.match(summarizeTaskError("ConnectError"), /不一定是额度/);
  const task = readFileSync(new URL("../components/TaskSettings.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(task, /Use the preset’s default parameters/);
  assert.match(task, /knowledge: request.knowledge/);
});
