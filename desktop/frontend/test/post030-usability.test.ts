import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { nativeDropPaths } from "../lib/fileDrop";
import { KnowledgeDocument } from "../components/KnowledgeDocument";
import { TaskLogBrowser } from "../components/TaskLogBrowser";
import { BilingualKnowledgeImport } from "../components/BilingualKnowledgeImport";
import { hydratePreferences } from "../lib/preferences";
import { initialState } from "../lib/state";

test("native file drops preserve multiple full paths, reject invalid values and deduplicate", () => {
  const event = { detail: { paths: ["D:/中文/a.mp4", "d:/中文/A.MP4", null, 4, "", "bad\0path", "E:/字幕/b.wav"] } } as unknown as Event;
  assert.deepEqual(nativeDropPaths(event), ["D:/中文/a.mp4", "E:/字幕/b.wav"]);
  assert.deepEqual(nativeDropPaths({ detail: { path: "D:/legacy.mp4" } } as unknown as Event), ["D:/legacy.mp4"]);
  assert.deepEqual(nativeDropPaths({} as Event), []);
});

test("knowledge reader removes template comments but escapes imported text and never changes source", () => {
  const text = "# 测试\n<!-- hidden instructions\nmore -->\n## 译名\n原文 → 翻译\n<script>alert(1)</script>";
  const html = renderToStaticMarkup(createElement(KnowledgeDocument, { text, empty: "empty" }));
  assert.match(html, /<h3>译名<\/h3>/);
  assert.match(html, /原文 → 翻译/);
  assert.doesNotMatch(html, /hidden instructions|<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(text, /hidden instructions/);
});

test("log browser announces ten-record pages and separates open-location actions", () => {
  const html = renderToStaticMarkup(createElement(TaskLogBrowser, { tasksPath: "D:/任务/tasks" }));
  assert.match(html, /每页 10 条/);
  assert.match(html, /aria-label="日志分页"/);
  assert.match(html, /共 0 条/);
  const source = readFileSync(new URL("../components/TaskLogBrowser.tsx", import.meta.url), "utf8");
  assert.match(source, /const PAGE_SIZE = 10/);
  assert.match(source, /if \(id !== sequence.current\) return/);
});

test("collapsed settings auto-expand for guided field navigation and Agent rows retain configuration", () => {
  const source = readFileSync(new URL("../components/Settings.tsx", import.meta.url), "utf8");
  assert.equal((source.match(/<details className="settings-section/g) || []).length, 2);
  assert.match(source, /parent instanceof HTMLDetailsElement/);
  assert.doesNotMatch(source, /className="agent-status-list"/);
  assert.match(source, /<AgentConfigDialog/);
  assert.match(source, /inputId=\{\x60api-key-\$\{provider.id\}/);
  const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /error.code === "asr_credentials_required" \? "credentials"/);
});

test("knowledge import uses the core-specific Agent and does not silently substitute stale saved choices", () => {
  hydratePreferences({ ui: { rememberLastSettings: true, knowledgeImportOptions: { llm_source: "agent", llm_agent: "LOCAL_WORKBUDDY" } }, task_defaults: {} });
  const html = renderToStaticMarkup(createElement(BilingualKnowledgeImport, {
    snapshot: null, tasks: [], routing: { ...initialState.routing, unified_llm_media: true }, onApplied: async () => {},
  }));
  assert.match(html, /LOCAL_CODEBUDDY/);
  assert.match(html, /不会自动切换/);
  assert.match(html, /LOCAL_WORKBUDDY · 需重新选择/);
  assert.match(html, /手动指定模型 ID/);
});
