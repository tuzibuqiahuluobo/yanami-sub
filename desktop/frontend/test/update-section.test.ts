import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";


test("a ready update restarts app patches but only exits for full updates", () => {
  const source = readFileSync(
    new URL("../components/UpdateSection.tsx", import.meta.url),
    "utf8",
  );

  assert.match(
    source,
    /if \(install\.exit_required\) \{\s*await onCloseWindow\(\);\s*\} else \{\s*await onRestartApplication\(\);/,
  );
  assert.match(source, /disabled=\{updateBusy\}/);
});


test("download progress is root-owned instead of an inline Settings bar", () => {
  const page = readFileSync(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const section = readFileSync(
    new URL("../components/UpdateSection.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /\[updateInstall, setUpdateInstall\]/);
  assert.match(page, /setInterval\(\(\) => void pollUpdateInstall\(\), 500\)/);
  assert.match(page, /<ToastViewport updateInstall=\{updateInstall\}/);
  assert.match(section, /updateInstall: UpdateInstallSnapshot \| null/);
  assert.doesNotMatch(section, /onGetUpdateInstall/);
  assert.doesNotMatch(section, /update-progress-bar/);
});
