import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createDesktopApi } from "../lib/bridge";
import { knowledgeOutcome } from "../components/BilingualKnowledgeImport";

test("knowledge review uses native draft IDs, never re-generates on apply", async () => {
  const calls: unknown[][] = [];
  const previous = globalThis.window;
  Object.assign(globalThis, { window: { location: { search: "" }, pywebview: { api: {
    run_bilingual_knowledge_update: async (request: unknown) => { calls.push(["generate", request]); return { ok: true, data: { draft_id: "draft", status: "generated" } }; },
    apply_knowledge_proposal: async (id: string) => { calls.push(["apply", id]); return { ok: true, data: { status: "no_change" } }; },
    select_subtitle_file: async () => ({ ok: true, data: { path: "a.srt" } }),
  } } } });
  try {
    const api = createDesktopApi({ preview: false });
    const report = await api.runBilingualKnowledgeUpdate({ source_srt: "a.srt", refined_srt: "b.srt", subject: "common/a", execute: true, request: { input: "a.srt", llm_source: "agent", llm_agent: "LOCAL_DSH" } });
    await api.applyKnowledgeProposal(report.draft_id!);
    assert.deepEqual(calls[1], ["apply", "draft"]);
    assert.equal(calls.length, 2);
    assert.equal((await api.selectSubtitleFile()).path, "a.srt");
  } finally { Object.assign(globalThis, { window: previous }); }
});

test("outcomes distinguish generation, no change, partial and actual commit", () => {
  assert.match(knowledgeOutcome({ status: "generated" }, true), /尚未写入/);
  assert.match(knowledgeOutcome({ status: "no_change" }, false), /unchanged/);
  assert.match(knowledgeOutcome({ status: "partial" }, true), /部分/);
  assert.match(knowledgeOutcome({ status: "applied" }, false), /committed/);
});

test("knowledge confirmations are themed and keyboard accessible", () => {
  const page = readFileSync(new URL("../components/KnowledgeCenter.tsx", import.meta.url), "utf8");
  const dialog = readFileSync(new URL("../components/ConfirmDialog.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(page, /window\.confirm/);
  assert.match(dialog, /aria-modal="true"/);
  assert.match(dialog, /event.key === "Escape"/);
  assert.match(dialog, /querySelectorAll/);
  assert.match(page, /applyKnowledgeProposal\(refinedProposal.draft_id\)/);
});
