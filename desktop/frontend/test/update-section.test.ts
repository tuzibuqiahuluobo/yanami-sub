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


test("preview updates are a separate persisted choice from automatic checks", () => {
  const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  const section = readFileSync(new URL("../components/UpdateSection.tsx", import.meta.url), "utf8");

  assert.match(page, /saveUi\(\{ previewUpdates: enabled \}\)/);
  assert.match(page, /isPreviewVersion\(payload\.app_version\)/);
  assert.match(page, /desktopApi\.checkUpdates\(previewUpdates\)/);
  assert.match(section, /checked=\{previewUpdates\}/);
  assert.match(section, /setAvailableUpdate\(null\)/);
  assert.match(section, /if \(generation !== checkGeneration\.current\) return/);
});


test("subtitle progress follows the task across pages and reuses completion feedback", () => {
  const page = readFileSync(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const toast = readFileSync(
    new URL("../components/ToastProvider.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /<ToastViewport updateInstall=\{updateInstall\} task=\{state\.task\} route=\{state\.route\}/);
  assert.match(toast, /route !== "new-task" && task\.phase === "running"/);
  assert.match(toast, /<TaskProgressItem task=\{task\}/);
  assert.match(toast, /t\.processing\.stages\.translatedSrt/);
  assert.match(toast, /progress \? "" : " is-indeterminate"/);
  assert.match(toast, /progress\.completed\}\/\$\{progress\.total\}/);
  assert.match(page, /showSuccess\(t\.toast\.taskCompleted/);
});
