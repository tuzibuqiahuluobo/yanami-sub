import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SoundSettings } from "../components/SoundSettings";
import { Feedback } from "../components/Feedback";
import { DEFAULT_SOUND, playNotification, soundSettings } from "../lib/notificationSound";
import { hydratePreferences } from "../lib/preferences";
import { readStylesheet } from "./stylesheet";
import { WORKBUDDY_QUICK_SETTINGS } from "../components/TaskSettings";

test("sound defaults to enabled at 50% and disabled/zero is silent", async () => {
  hydratePreferences({ ui: {}, task_defaults: {} });
  assert.deepEqual(soundSettings(), DEFAULT_SOUND);
  assert.match(renderToStaticMarkup(createElement(SoundSettings)), /50%/);
  hydratePreferences({ ui: { sound: { enabled: false, volume: 0 } }, task_defaults: {} });
  assert.equal(await playNotification("task"), false);
  assert.equal(soundSettings().volume, 0);
});
test("feedback states local-only collection, privacy and GitHub final submission", () => {
  const html = renderToStaticMarkup(createElement(Feedback));
  assert.match(html, /自动获取日志（本地）/);
  assert.match(html, /不会自动上传/);
  assert.match(html, /可访问 GitHub 的代理/);
  assert.match(html, /系统默认浏览器/);
  assert.equal([...html.matchAll(/新建 GitHub Issue/g)].length, 1);
  assert.doesNotMatch(html, /在浏览器继续/);
  const bridge = readFileSync(new URL("../lib/bridge.ts", import.meta.url), "utf8");
  assert.match(bridge, /collect_feedback_logs/);
  assert.match(bridge, /open_feedback_issue/);
  const sound = readFileSync(new URL("../lib/notificationSound.ts", import.meta.url), "utf8");
  assert.match(sound, /\.\/sounds\/completion.wav/);
});

test("sound controls have named switches, a labeled range and preserve muted event choices", () => {
  hydratePreferences({ ui: { sound: { enabled: false, task: true, batch: false, download: true, volume: 75 } }, task_defaults: {} });
  const html = renderToStaticMarkup(createElement(SoundSettings));
  assert.equal([...html.matchAll(/role="switch"/g)].length, 4);
  assert.equal([...html.matchAll(/disabled=""/g)].length, 3);
  assert.match(html, /aria-label="启用提示音"/);
  assert.match(html, /for="notification-volume"/);
  assert.match(html, /id="notification-volume"[^>]*type="range"/);
  assert.match(html, /75%/);
  assert.equal(soundSettings().task, true);
  assert.equal(soundSettings().batch, false);
  assert.equal(soundSettings().download, true);
  const css = readStylesheet();
  assert.match(css, /\.sound-switch input:focus-visible/);
  assert.match(css, /\.sound-events \{ grid-template-columns: 1fr;/);
  assert.match(css, /var\(--accent\) 0 var\(--sound-volume\)/);
  assert.match(css, /"sidebar" 50px\s*\/ minmax\(0, 1fr\)/);
});

test("Agent settings use native pickers and distinguish CLI readiness from account readiness", () => {
  const settings = readFileSync(new URL("../components/Settings.tsx", import.meta.url), "utf8");
  assert.match(settings, /desktopApi\.selectAgentPath\(tier, kind\)/);
  assert.match(settings, /chooseAgentPath\(tier, "file"\)/);
  assert.match(settings, /chooseAgentPath\(tier, "directory"\)/);
  assert.match(settings, /readOnly[\s\S]*aria-describedby="agent-path-selection-hint"/);
  assert.match(settings, /"CLI ready" : "CLI 就绪"/);
});

test("WorkBuddy quick settings are explicit, preserve safety gates and cover both task forms", () => {
  assert.deepEqual(WORKBUDDY_QUICK_SETTINGS, {
    llm_difficulty: "efficiency", llm_retrieval: "none", llm_media: "text",
    llm_correction_media: "text", llm_planning_media: "text", knowledge: "none", llm_fast: "auto",
  });
  assert.equal("llm_source" in WORKBUDDY_QUICK_SETTINGS, false);
  assert.equal("llm_model" in WORKBUDDY_QUICK_SETTINGS, false);
  assert.equal("llm_agent" in WORKBUDDY_QUICK_SETTINGS, false);
  assert.equal("llm_parallel_windows" in WORKBUDDY_QUICK_SETTINGS, false);
  const source = readFileSync(new URL("../components/TaskSettings.tsx", import.meta.url), "utf8");
  assert.match(source, /source === "agent" && request.llm_agent === "LOCAL_WORKBUDDY"/);
  assert.match(source, /selectedRoute.startsWith\("local-workbuddy-"\)/);
  assert.match(source, /onClick=\{\(\) => onChange\(WORKBUDDY_QUICK_SETTINGS\)\}/);
  for (const form of ["NewTask", "BatchQueue"]) {
    const component = readFileSync(new URL(`../components/${form}.tsx`, import.meta.url), "utf8");
    assert.match(component, /<TaskSettings/);
  }
});
