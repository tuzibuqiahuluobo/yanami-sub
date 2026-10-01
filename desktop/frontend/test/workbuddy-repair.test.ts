import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { WorkBuddyRepairDialog } from "../components/WorkBuddyRepairDialog";

test("WorkBuddy repair uses a separate accessible official-client dialog", () => {
  const props = { open: true, onClose: () => {}, onProbe: async () => [] };
  const html = renderToStaticMarkup(createElement(WorkBuddyRepairDialog, props));
  assert.match(html, /role="dialog"/);
  assert.match(html, /aria-modal="true"/);
  assert.match(html, /不读取或保存厂商登录凭据/);
  assert.match(html, /打开 WorkBuddy/);
  assert.match(html, /重新检测 CLI/);
  assert.equal(renderToStaticMarkup(createElement(WorkBuddyRepairDialog, { ...props, open: false })), "");
});

test("WorkBuddy repair keeps keyboard focus and does not call a model", () => {
  const source = readFileSync(new URL("../components/WorkBuddyRepairDialog.tsx", import.meta.url), "utf8");
  assert.match(source, /event.key === "Escape"/);
  assert.match(source, /event.key !== "Tab"/);
  assert.match(source, /previous\?\.focus\(\)/);
  assert.match(source, /登录、模型权限和额度尚未验证/);
  assert.match(source, /desktopApi.openWorkBuddyLogin\(\)/);
  assert.doesNotMatch(source, /startTask\(|saveApiKeys\(|revealApiKeys\(/);
});
