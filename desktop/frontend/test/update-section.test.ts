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
