import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import test from "node:test";
import { AgentCooperation } from "../components/AgentCooperation";
import { KnowledgeRecovery } from "../components/KnowledgeRecovery";

test("cooperation and recovery require explicit actions and explain their boundaries", () => {
  const agent = renderToStaticMarkup(createElement(AgentCooperation));
  assert.match(agent, /conversational-agent/);
  assert.match(agent, /一小时/);
  assert.match(agent, /不会自动启动/);
  const recovery = renderToStaticMarkup(createElement(KnowledgeRecovery, { onChanged: async () => {} }));
  assert.match(recovery, /不恢复配置和密钥/);
  assert.match(recovery, /校验并准备副本/);
  assert.doesNotMatch(recovery, /启用已准备的副本/);
});

test("one task-settings implementation controls batch presets and intake uses its saved request", () => {
  const task = readFileSync(new URL("../components/TaskSettings.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(task, /Use the preset’s default parameters/);
  assert.match(task, /knowledge: request.knowledge/);
  assert.match(task, /llm_preset_defaults: false/);
  const batch = readFileSync(new URL("../components/BatchQueue.tsx", import.meta.url), "utf8");
  assert.match(batch, /desktopApi\.appendBatch\(snapshot\.batch_id, sources\)/);
  assert.match(batch, /沿用本批次保存的参数/);
  assert.match(batch, /<TaskSettings/);
});
