import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { chromium } from "playwright-core";
import { readStylesheet } from "./stylesheet";

test("knowledge actions stay within half-width cards at narrow widths and large font sizes", async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [375, 800, 1024, 1280, 1600]) {
      for (const size of [16, 20]) {
        await page.setViewportSize({ width, height: 950 });
        for (const labels of [["查看计划（不调用模型）", "生成建议（调用模型，不写入）", "生成并写入（调用模型）"], ["View plan (no model call)", "Generate suggestions (model call, no write)", "Generate & write (model call)"]]) {
          await page.setContent(`<style>${readStylesheet()}body{overflow:auto}html{--base-font-size:${size}px}</style><main class="page-knowledge" style="padding:24px"><div class="knowledge-maintenance-grid">${[0, 1].map(() => `<section class="primary-panel knowledge-section"><div class="knowledge-command-group"><strong>知识库 / Knowledge</strong>${labels.map(label => `<button class="button button-secondary">${label}</button>`).join("")}</div></section>`).join("")}</div></main>`);
          const clipped = await page.locator(".button").evaluateAll(buttons => buttons.some(button => {
            const box = button.getBoundingClientRect(), panel = button.closest("section")!.getBoundingClientRect();
            return box.left < panel.left || box.right > panel.right + 1;
          }));
          assert.equal(clipped, false, `${width}px / ${size}px / ${labels[0]}`);
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
        }
      }
    }
  } finally { await browser.close(); }
});

test("knowledge file errors stay near the refinement form and selectors reuse rounded menus", () => {
  const page = readFileSync(new URL("../components/KnowledgeCenter.tsx", import.meta.url), "utf8");
  const bilingual = readFileSync(new URL("../components/BilingualKnowledgeImport.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page + bilingual, /<select\b/);
  assert.match(page, /source_srt: sourcePath.trim\(\)/);
  assert.match(page, /refinedError.*role="alert"/);
  assert.match(page, /setError\(""\); setOutput\(""\)/);
  assert.match(bilingual, /role="status"/);
});
