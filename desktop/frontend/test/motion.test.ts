import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { DEFAULT_APPEARANCE } from "../lib/useAppearance";
import { readStylesheet } from "./stylesheet";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

// These check agreements that span two files, where neither side can tell it
// has been broken: a class the stylesheet styles but nothing renders, a switch
// with no stylesheet behind it. Assertions about a single file's own wording
// belong nowhere -- they only restate the file back to itself.

test("the moving pill the sidebar renders is the one the stylesheet drives", () => {
  const sidebar = read("../components/Sidebar.tsx");
  const css = readStylesheet();

  assert.match(sidebar, /className="nav-active-pill"/);
  assert.match(sidebar, /"--active-index"/);
  assert.match(css, /\.nav-active-pill\b/);
  assert.match(css, /var\(--active-index\)/);
});

test("motion can be turned off, by the user and by the system", () => {
  const appearance = read("../lib/useAppearance.ts");
  const css = readStylesheet();

  // The setting writes an attribute; the stylesheet is what honours it.
  assert.match(appearance, /animations: boolean/);
  assert.match(appearance, /data-motion/);
  assert.match(css, /\[data-motion="off"\]/);
  assert.match(css, /prefers-reduced-motion: reduce/);
});

test("theme-coloured switchers share the animation preference gate", () => {
  const helper = read("../lib/viewTransition.ts");
  const settings = read("../components/Settings.tsx");
  const taskSettings = read("../components/TaskSettings.tsx");
  const knowledge = read("../components/KnowledgeCenter.tsx");
  const css = readStylesheet();

  assert.match(helper, /documentElement\.dataset\.motion === "off"/);
  assert.match(helper, /prefers-reduced-motion: reduce/);
  assert.match(settings, /runInterfaceTransition/);
  assert.match(taskSettings, /runInterfaceTransition/);
  assert.match(knowledge, /runInterfaceTransition/);
  assert.match(css, /view-transition-name: active-task-tab/);
  assert.match(css, /view-transition-name: active-knowledge-tab/);
  assert.match(css, /\[data-motion="off"\] \.task-tab\.is-active/);
  assert.match(css, /\[data-motion="off"\] \.knowledge-tabs button\.is-active/);
});

test("the routing catalog has an accessible two-way reveal", () => {
  const settings = read("../components/Settings.tsx");
  const css = readStylesheet();

  assert.match(settings, /className="routing-catalog-toggle"/);
  assert.match(settings, /aria-expanded=\{routingCatalogOpen\}/);
  assert.match(settings, /className="routing-catalog-reveal"/);
  assert.match(css, /\.routing-catalog-reveal\s*\{[\s\S]*?grid-template-rows: 0fr/);
  assert.match(css, /\.routing-catalog\.is-open \.routing-catalog-reveal\s*\{[\s\S]*?grid-template-rows: 1fr/);
});

test("highlighted form controls share the rounded control token", () => {
  const css = readStylesheet();

  assert.match(css, /--radius-control:\s*14px/);
  assert.match(css, /\.url-row input\s*\{[\s\S]*?border-radius: var\(--radius-control\)/);
  assert.match(css, /\.batch-url-row textarea\s*\{[\s\S]*?border-radius: var\(--radius-control\)/);
  assert.match(css, /\.custom-select-trigger\s*\{[\s\S]*?border-radius: var\(--radius-control\)/);
  assert.match(css, /\.knowledge-search\s*\{[\s\S]*?border-radius: var\(--radius-control\)/);
});

test("a first run starts with the light theme", () => {
  assert.equal(DEFAULT_APPEARANCE.theme, "light");
  assert.equal(DEFAULT_APPEARANCE.animations, true);
});

test("the animations stay native to the platform", () => {
  // View transitions and CSS keyframes only -- an animation library would be
  // several hundred KB in a window that ships its own runtime already.
  const packageJson = read("../package.json");

  assert.doesNotMatch(packageJson, /framer-motion|motion-one|gsap/);
});
