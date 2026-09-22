import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { translations } from "../lib/translations";


test("translation mode discloses API processing", () => {
  const component = readFileSync(
    new URL("../components/NewTask.tsx", import.meta.url),
    "utf8",
  );

  assert.match(component, /cloudTranslation/);
  assert.match(component, /privacyNoteCloud/);
  // Read through the module rather than the file: the copy lives in one file
  // per language now, and what has to carry the disclosure is the value the UI
  // renders, not whichever file happens to hold it.
  assert.match(
    translations.zh.newTask.privacyNoteCloud,
    /使用 API 模型时，任务所需内容会发送给对应服务/,
  );
  assert.match(
    translations.en.newTask.privacyNoteCloud,
    /API models receive only the content required for the task/,
  );
});
