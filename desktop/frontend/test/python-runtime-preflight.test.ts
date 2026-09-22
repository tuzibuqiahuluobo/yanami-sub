import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { translations } from "../lib/translations";


function read(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}


test("Python setup checks locally before offering a download", () => {
  const manager = read("../components/ResourceManager.tsx");
  const page = read("../app/page.tsx");

  assert.match(
    page,
    /onCheckPythonInterpreter=\{\(\) => desktopApi\.getPythonInterpreter\(\)\}/,
  );
  assert.match(manager, /pythonPreflightBusy/);
  assert.match(manager, /resources\.confirm\.python\.useLocal/);
  assert.match(manager, /resources\.confirm\.python\.choose/);
  assert.match(manager, /resources\.confirm\.python\.download/);
  assert.match(manager, /aria-live="polite"/);
});


test("Python preflight choices are localized and explain interpreter reuse", () => {
  assert.match(translations.zh.resources.confirm.python.checking, /12 秒/);
  assert.match(translations.zh.resources.confirm.python.found, /不再下载解释器/);
  assert.match(translations.zh.resources.confirm.python.download, /下载 Python/);
  assert.match(translations.en.resources.confirm.python.checking, /12 seconds/);
  assert.match(translations.en.resources.confirm.python.found, /without downloading/);
});
