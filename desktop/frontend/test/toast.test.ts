import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { readStylesheet } from "./stylesheet";


const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");


test("success toasts are bounded, dismissible and announced without taking focus", () => {
  const source = read("../components/ToastProvider.tsx");

  assert.match(source, /slice\(-3\)/);
  assert.match(source, /window\.setTimeout\([^,]+, 4500\)/);
  assert.match(source, /aria-live="polite"/);
  assert.match(source, /role="status"/);
  assert.match(source, /aria-label=\{t\.toast\.close\}/);
  assert.doesNotMatch(source, /\.focus\(/);
});


test("the update download is a circular lower-right status with a checked finish", () => {
  const source = read("../components/ToastProvider.tsx");
  const css = readStylesheet();

  assert.match(source, /role="progressbar"/);
  assert.match(source, /aria-valuenow=\{determinate \? Math\.round\(percent\) : undefined\}/);
  assert.match(source, /className="update-ring-value"/);
  assert.match(source, /t\.toast\.updateDownloaded/);
  assert.match(source, /<Check size=\{14\}/);
  assert.match(css, /\.toast-viewport\s*\{[\s\S]*?right: 24px;[\s\S]*?bottom: 24px/);
  assert.match(css, /\.update-ring-value\s*\{[\s\S]*?stroke-dasharray: 100/);
  assert.match(css, /\[data-motion="off"\] \.update-ring-value/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});


test("explicit successful operations route through the shared toast", () => {
  for (const file of [
    "../components/ApiKeyField.tsx",
    "../components/BatchQueue.tsx",
    "../components/KnowledgeCenter.tsx",
    "../components/ResourceManager.tsx",
    "../components/Settings.tsx",
  ]) {
    const source = read(file);
    assert.match(source, /useToast/);
    assert.match(source, /showSuccess\(/);
  }

  const page = read("../app/page.tsx");
  assert.match(page, /t\.toast\.taskCompleted/);
  assert.match(page, /t\.toast\.resourceInstalled/);
});
