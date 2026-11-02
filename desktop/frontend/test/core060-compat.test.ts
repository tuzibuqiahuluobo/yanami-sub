import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { WorkBuddyRepairDialog } from "../components/WorkBuddyRepairDialog";
import { createDesktopApi } from "../lib/bridge";
import { translations } from "../lib/translations";

test("automatic install intent reaches the backend separately from a manual repair click", async () => {
  const previous = globalThis.window;
  const calls: unknown[][] = [];
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    location: { search: "" }, pywebview: { api: {
      install_resource: async (...args: unknown[]) => { calls.push(args); return { ok: true, data: { resource_id: "uv", state: "queued" } }; },
    } },
  } });
  try {
    const api = createDesktopApi({ preview: false });
    await api.installResource("uv", true);
    await api.installResource("uv");
    assert.deepEqual(calls, [["uv", true], ["uv", false]]);
    const page = readFileSync("app/page.tsx", "utf-8");
    assert.match(page, /installResource\(missing.id, true\)/);
  } finally {
    if (previous === undefined) Reflect.deleteProperty(globalThis, "window");
    else Object.defineProperty(globalThis, "window", { configurable: true, value: previous });
  }
});

test("independent CodeBuddy repair explains separate credentials and account/site requirements", () => {
  const html = renderToStaticMarkup(createElement(WorkBuddyRepairDialog, {
    open: true, codeBuddy: true, onClose() {}, onProbe: async () => [],
  }));
  assert.match(html, /CodeBuddy CLI 登录修复/);
  assert.match(html, /@tencent-ai\/codebuddy-code/);
  assert.match(html, /Chinese Site.*International Site/);
  assert.match(html, /不会复用 WorkBuddy 桌面凭据/);
  assert.match(html, /打开 CodeBuddy CLI/);
  assert.doesNotMatch(html, /打开官方 WorkBuddy 桌面客户端/);
});

test("CodeBuddy login uses its own explicit native action without a model request", async () => {
  const previous = globalThis.window;
  const calls: string[] = [];
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    location: { search: "" }, pywebview: { api: {
      open_codebuddy_login: async () => { calls.push("login"); return { ok: true, data: { path: "D:/npm/bin/codebuddy" } }; },
    } },
  } });
  try {
    const api = createDesktopApi({ preview: false });
    assert.deepEqual(calls, []);
    assert.equal((await api.openCodeBuddyLogin()).path, "D:/npm/bin/codebuddy");
    assert.deepEqual(calls, ["login"]);
  } finally {
    if (previous === undefined) Reflect.deleteProperty(globalThis, "window");
    else Object.defineProperty(globalThis, "window", { configurable: true, value: previous });
  }
});

test("knowledge read mode is described as read-only in both languages", () => {
  assert.match(translations.zh.newTask.settings.knowledgeCollect, /只读.*不写入/);
  assert.match(translations.en.newTask.settings.knowledgeCollect, /Read.*without updates/);
});
