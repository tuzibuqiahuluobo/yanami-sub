import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { chromium } from "playwright-core";

import { importedStylesheets, readStylesheet } from "./stylesheet";


test("every file in app/styles is imported, and in one order", () => {
  // The sheet is split across files now, and `globals.css` is the only thing
  // that knows they exist. A new file nobody imports contributes no styles at
  // all -- and the failure is a component that quietly renders unstyled, not
  // an error anyone sees. The reverse (an import naming a file that is gone)
  // breaks the build, so only this direction needs watching.
  const imported = importedStylesheets();
  const onDisk = readdirSync(new URL("../app/styles/", import.meta.url))
    .filter((name) => name.endsWith(".css"))
    .sort();

  assert.deepEqual(
    imported.map((path) => path.replace("./styles/", "")).sort(),
    onDisk,
  );
  // Order is the cascade: same specificity, later wins. Dark overrides only
  // work because they come after the components they repaint.
  const dark = imported.indexOf("./styles/dark.css");
  const appearance = imported.indexOf("./styles/appearance.css");
  // Both explicitly: `indexOf` answers -1 for a file that is gone, and
  // `15 > -1` would let this assertion pass while testing nothing.
  assert.ok(dark >= 0 && appearance >= 0);
  assert.ok(dark > appearance);
  assert.equal(imported.at(-1), "./styles/fallbacks.css");
});


test("knowledge status and maintenance actions fit their real state", () => {
  const source = readFileSync(
    new URL("../components/KnowledgeCenter.tsx", import.meta.url),
    "utf8",
  );
  const css = readFileSync(
    new URL("../app/styles/knowledge.css", import.meta.url),
    "utf8",
  );

  assert.match(source, /loading \? \([\s\S]*?t\.knowledge\.loading/);
  assert.match(source, /\) : snapshot \? \([\s\S]*?snapshot\.revision/);
  assert.doesNotMatch(
    source,
    /snapshot \? `rev \$\{snapshot\.revision\}` : t\.knowledge\.loading/,
  );
  assert.match(
    css,
    /@media \(max-width: 1200px\)[\s\S]*?\.knowledge-command-group\s*\{[\s\S]*?grid-template-columns: repeat\(3, max-content\)/,
  );
});


test("dark resource surfaces stay neutral and the installation log stays dark", { timeout: 30_000 }, async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`
      <style>${readStylesheet()}</style>
      <div class="app-shell">
        <aside class="sidebar"></aside>
        <main class="workspace">
          <section class="resource-card">
            <pre class="resource-install-log">Downloading Whisper...</pre>
          </section>
        </main>
      </div>
    `);
    const appearance = () => page.evaluate(() => ({
      workspace: getComputedStyle(document.querySelector(".workspace")!).backgroundColor,
      sidebar: getComputedStyle(document.querySelector(".sidebar")!).backgroundColor,
      panel: getComputedStyle(document.querySelector(".resource-card")!).backgroundColor,
      log: getComputedStyle(document.querySelector(".resource-install-log")!).backgroundColor,
    }));
    const light = await appearance();
    await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
    const dark = await appearance();
    assert.equal(dark.workspace, "rgb(25, 27, 29)");
    assert.equal(dark.sidebar, "rgb(32, 34, 37)");
    assert.equal(dark.panel, "rgba(43, 45, 49, 0.75)");
    assert.equal(dark.log, "rgb(29, 31, 34)");
    assert.notEqual(dark.log, light.log);
    assert.notEqual(dark.panel, light.panel);
    await page.evaluate(() => document.documentElement.style.setProperty("--glass-opacity", "0.4"));
    assert.equal((await appearance()).panel, "rgba(43, 45, 49, 0.4)");
  } finally {
    await browser.close();
  }
});
