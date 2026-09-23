import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { UPDATE_HISTORY, updateHistoryFor } from "../lib/updateHistory";


test("an available startup update opens an in-app announcement", () => {
  const page = readFileSync(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const announcement = readFileSync(
    new URL("../components/UpdateAnnouncement.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /<UpdateAnnouncement/);
  assert.match(page, /startUpdateInstall\(startupUpdate\.kind, startupUpdate\.version\)/);
  assert.match(page, /dispatch\(\{ type: "navigate", route: "settings" \}\)/);
  assert.match(announcement, /role="dialog"/);
  assert.match(announcement, /aria-modal="true"/);
  assert.match(announcement, /onOpenUpdatePage/);
});


test("do not show again controls the same automatic-check preference as Settings", () => {
  const page = readFileSync(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const section = readFileSync(
    new URL("../components/UpdateSection.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /changeAutoUpdateCheck\(false\)/);
  assert.match(page, /saveUi\(\{ autoUpdateCheck: enabled \}\)/);
  assert.match(section, /checked=\{autoCheck\}/);
  assert.match(section, /onAutoCheckChange\(event\.target\.checked\)/);
  assert.doesNotMatch(section, /uiValue<boolean>\("autoUpdateCheck"/);
});


test("history stays bundled and unrendered until the user loads it", () => {
  const source = readFileSync(
    new URL("../components/UpdateAnnouncement.tsx", import.meta.url),
    "utf8",
  );

  assert.equal(UPDATE_HISTORY.length, 10);
  assert.equal(updateHistoryFor("zh")[0]?.version, "0.1.0-rc.6.post2");
  assert.equal(updateHistoryFor("en").at(-1)?.version, "0.1.0-rc.3");
  assert.match(source, /historyLoaded \? \(/);
  assert.match(source, /setHistoryLoaded\(\(value\) => !value\)/);
  assert.match(source, /aria-expanded=\{historyLoaded\}/);
});
