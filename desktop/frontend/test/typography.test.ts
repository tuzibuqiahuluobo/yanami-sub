import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { readStylesheet } from "./stylesheet";


const css = readStylesheet();
const layout = readFileSync(
  new URL("../app/layout.tsx", import.meta.url),
  "utf8",
);
const titleBar = readFileSync(
  new URL("../components/TitleBar.tsx", import.meta.url),
  "utf8",
);
const page = readFileSync(
  new URL("../app/page.tsx", import.meta.url),
  "utf8",
);


test("the complete UI uses Windows system fonts at readable sizes", () => {
  assert.match(css, /font-family:\s*var\(--user-font,\s*"Microsoft YaHei UI"\)/);
  assert.match(css, /html\s*\{[\s\S]*font-size:\s*var\(--base-font-size\)/);
  assert.doesNotMatch(css, /^\s*font-size:\s*\d+(?:\.\d+)?px;/m);
  assert.ok([...css.matchAll(/font-size:\s*[\d.]+rem/g)].length > 30);
});


test("the UI does not bundle web fonts", () => {
  const fontFaces = [...css.matchAll(/@font-face\s*\{([\s\S]*?)\}/g)].map(
    (match) => match[1],
  );
  assert.equal(fontFaces.length, 0);
  assert.doesNotMatch(css, /\.woff2/);
});


test("Yanami Sub metadata and title bar use the supplied icon", () => {
  assert.match(layout, /title:\s*"Yanami Sub"/);
  assert.match(layout, /href="\.\/icon\.png"/);
  assert.match(titleBar, /src="\.\/icon\.png"/);
  assert.doesNotMatch(titleBar, /brand-glyph/);
  assert.match(titleBar, /className="brand-icon"/);
  assert.match(titleBar, /<span>Yanami Sub<\/span>/);
  assert.doesNotMatch(page, /className="brand-glyph"/);
});


test("character themes include the requested Marisa and Yanami palettes", () => {
  assert.match(
    css,
    /\[data-accent="marisa"\][\s\S]*?#f9f8f2[\s\S]*?#86550d[\s\S]*?#ffffff/,
  );
  assert.match(css, /\[data-accent="yanami"\]/);
  assert.match(css, /#f5f8f7[\s\S]*?#315f88[\s\S]*?#53783f/);
  const appearance = readFileSync(new URL("../lib/useAppearance.ts", import.meta.url), "utf8");
  assert.match(appearance, /settings\.theme === "marisa" \|\| settings\.theme === "reimu" \|\| settings\.theme === "yanami"/);
  assert.match(appearance, /resolved = "light"/);
});
