import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createDesktopApi } from "../lib/bridge";
import { KnowledgeFileExchange } from "../components/KnowledgeFileExchange";

test("local exchange starts read-only and clearly separates importing from a full backup", () => {
  const html = renderToStaticMarkup(createElement(KnowledgeFileExchange, {
    snapshot: null, selected: "", onSelect: () => {}, busy: false, setBusy: () => {}, onChanged: async () => {},
  }));
  assert.match(html, /无需服务器、不调用模型/);
  assert.match(html, /不等同于完整备份/);
  assert.match(html, /先核对预览/);
  assert.match(html, /disabled=""/);
  assert.doesNotMatch(html, /role="dialog"/);
});

test("preview never pretends native knowledge file operations succeeded", async () => {
  const api = createDesktopApi({ preview: true });
  await assert.rejects(api.selectKnowledgeDocument(), /desktop app/);
  await assert.rejects(api.exportKnowledgeEntry("common/example"), /desktop app/);
});

test("a completed local import refreshes both the entry document and source editor", () => {
  const page = readFileSync(new URL("../components/KnowledgeCenter.tsx", import.meta.url), "utf8");
  const callback = page.match(/<KnowledgeFileExchange[\s\S]*?onChanged=\{async \(\) => \{([\s\S]*?)\}\}/)?.[1];
  assert.ok(callback);
  assert.match(callback, /await loadSnapshot\(\)/);
  assert.match(callback, /await desktopApi\.getKnowledgeEntry\(selectedName\)/);
  assert.match(callback, /setDocument\(next\)/);
  assert.match(callback, /setDraft\(next\.text\)/);
});
