import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SoundSettings } from "../components/SoundSettings";
import { Feedback } from "../components/Feedback";
import { DEFAULT_SOUND, playNotification, soundSettings } from "../lib/notificationSound";
import { hydratePreferences } from "../lib/preferences";

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
  const bridge = readFileSync(new URL("../lib/bridge.ts", import.meta.url), "utf8");
  assert.match(bridge, /collect_feedback_logs/);
  assert.match(bridge, /open_feedback_issue/);
  const sound = readFileSync(new URL("../lib/notificationSound.ts", import.meta.url), "utf8");
  assert.match(sound, /\.\/sounds\/completion.wav/);
});
