import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ConfigMigration, migrationConfirmation } from "../components/ConfigMigration";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { createDesktopApi } from "../lib/bridge";

const plan = { status: "ready" as const, config_path: "D:/中文/config.toml",
  changes: ["correction_media → media = text"], issues: [], token: "f".repeat(64) };

test("config conversion starts with a read-only action and mandatory per-preview confirmation", () => {
  const html = renderToStaticMarkup(createElement(ConfigMigration));
  assert.match(html, /预览转换|Preview conversion/);
  assert.doesNotMatch(html, /role="dialog"/);
  for (const language of ["zh", "en"]) {
    const config = migrationConfirmation(plan, language);
    assert.equal(config.allowRemember, false);
    assert.match(config.message, /correction_media/);
    assert.match(config.message, /D:\/中文\/config.toml/);
    assert.doesNotMatch(config.message, new RegExp(plan.token));
    const dialog = renderToStaticMarkup(createElement(ConfirmDialog, {
      config, open: true, onConfirm() {}, onCancel() {},
    }));
    assert.match(dialog, /aria-modal="true"/);
    assert.match(dialog, /overflow-wrap:anywhere/);
    assert.doesNotMatch(dialog, /dialog-remember/);
  }
  const source = readFileSync("components/ConfigMigration.tsx", "utf-8");
  assert.match(source, /inFlight.current/);
  assert.match(source, /plan.status !== "ready"/);
  assert.match(source, /applyConfigMigration\(plan.token, true\)/);
  assert.match(source, /setPlan\(null\)/);
});

test("migration bridge cannot edit arbitrary paths and forwards explicit confirmation", async () => {
  const previous = globalThis.window, calls: unknown[][] = [];
  Object.defineProperty(globalThis, "window", { configurable: true, value: {
    location: { search: "" }, pywebview: { api: {
      preview_config_migration: async (...args: unknown[]) => { calls.push(["preview", ...args]); return { ok: true, data: plan }; },
      apply_config_migration: async (...args: unknown[]) => { calls.push(["apply", ...args]); return { ok: true, data: { status: "applied", backup_path: "D:/private-backup" } }; },
    } },
  } });
  try {
    const api = createDesktopApi({ preview: false });
    assert.deepEqual(calls, []);
    assert.equal((await api.previewConfigMigration()).token, plan.token);
    await api.applyConfigMigration(plan.token, true);
    assert.deepEqual(calls, [["preview"], ["apply", plan.token, true]]);
  } finally {
    if (previous === undefined) Reflect.deleteProperty(globalThis, "window");
    else Object.defineProperty(globalThis, "window", { configurable: true, value: previous });
  }
});
