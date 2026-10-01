import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("desktop startup Agent results suppress the second automatic scan", () => {
  const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /if \(payload\.startup_agent_statuses != null\) \{\s*setAgentStatuses\(payload\.startup_agent_statuses\);\s*\} else \{\s*void probeAgents\(\)/);
});
