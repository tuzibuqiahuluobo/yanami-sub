import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { chromium } from "playwright-core";
import { readStylesheet } from "./stylesheet";


const source = readFileSync(
  new URL("../components/CustomSelect.tsx", import.meta.url),
  "utf8",
);


test("custom select exposes complete keyboard navigation hooks", () => {
  for (const key of [
    "ArrowDown",
    "ArrowUp",
    "Home",
    "End",
    "Enter",
    " ",
    "Escape",
    "Tab",
  ]) {
    assert.match(source, new RegExp(`case [\"']${key === " " ? " " : key}[\"']`));
  }
  assert.match(source, /role="combobox"/);
  assert.match(source, /aria-label=/);
  assert.match(source, /aria-activedescendant/);
  assert.match(source, /aria-controls/);
  assert.match(source, /aria-labelledby/);
});

test("menus stay above later glass cards, scroll within the viewport, and receive the click", async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 900, height: 600 } });
    for (const theme of ["light", "dark"]) {
      await page.setContent(`<html data-theme="${theme}"><style>${readStylesheet()}</style><body>
        <section class="primary-panel page-knowledge" style="margin:40px"><ul popover="manual" role="listbox" class="custom-select-menu" style="left:100px;top:100px;bottom:auto;width:500px;max-height:250px">${Array.from({ length: 20 }, (_, i) => `<li class="custom-select-option" role="option">Task ${i}</li>`).join("")}</ul></section>
        <section class="primary-panel" style="position:absolute;left:80px;top:120px;width:600px;height:400px;z-index:999"><button id="underlying">Next selector</button></section>
        <script>document.querySelector('[popover]').showPopover(); window.clicked = ''; document.addEventListener('click', event => window.clicked = event.target.textContent);</script></body></html>`);
      const item = page.getByRole("option").nth(2);
      await item.click();
      assert.equal(await page.evaluate(() => (window as unknown as { clicked: string }).clicked), "Task 2");
      const menu = page.getByRole("listbox");
      assert.equal(await menu.evaluate(element => element.scrollHeight > element.clientHeight), true);
      const box = await menu.boundingBox();
      assert.ok(box && box.y >= 0 && box.y + box.height <= 600);
      await page.getByRole("option").last().scrollIntoViewIfNeeded();
      assert.equal(await menu.evaluate(element => element.scrollTop > 0), true);
    }
    assert.match(source, /popover="manual"/);
    assert.match(source, /showPopover/);
    assert.match(source, /event\.preventDefault\(\); event\.stopPropagation\(\); selectIndex/);
  } finally { await browser.close(); }
});
