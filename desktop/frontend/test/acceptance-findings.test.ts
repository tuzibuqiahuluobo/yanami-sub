import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { chromium } from "playwright-core";

import { pipelineModelsReady } from "../lib/resources";
import { readStylesheet } from "./stylesheet";


const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

// Regressions from the RC5.2 portable acceptance pass. Each one is a
// cross-file agreement -- the failure mode is two halves that disagree, which
// neither half can notice on its own.


test("the workspace pane does not capture the fixed dialog", () => {
  // The confirmation dialog is a child of `.workspace-view`. A keyframe
  // animation with `fill-mode: both` leaves its `to` declarations applied for
  // good, so an animated `transform` made that element a containing block and
  // every `position: fixed` inside it was positioned against the pane instead
  // of the viewport -- the dialog rendered outside the visible area on a
  // scrolled page, which read as a frozen UI.
  const css = readStylesheet();
  const workspaceView = css.match(
    /\.workspace-view\s*\{([\s\S]*?)\}/,
  )?.[1];

  assert.ok(workspaceView, ".workspace-view rule is gone");
  assert.doesNotMatch(
    workspaceView,
    /animation:/,
    "a `both`-filled animation on .workspace-view leaves a transform behind",
  );
  // No offset property at all, not merely `translate: none`: the
  // `@starting-style { translate: 10px }` attempt stayed applied and captured
  // the overlay exactly like the keyframe it replaced.
  assert.doesNotMatch(
    workspaceView,
    /\b(translate|transform|rotate|scale|filter|backdrop-filter|perspective|will-change|contain)\s*:/,
    "a containing-block property on .workspace-view captures fixed overlays",
  );
});

test(
  "a fixed overlay inside the scrolling pane still tracks the viewport",
  { timeout: 30_000 },
  async () => {
    // The behavioural half. A fixed overlay is sized to its containing block:
    // the viewport when nothing captures it, and the scrolling pane when an
    // ancestor is a containing block. The pane is genuinely narrower than the
    // window here (the shell is a grid with a sidebar), so the two cases are
    // told apart by a real measurement rather than by reading the CSS back.
    const browser = await chromium.launch({ channel: "msedge", headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: 900, height: 600 } });
      await page.setContent(`
        <style>${readStylesheet()}</style>
        <div class="app-shell">
          <section class="workspace">
            <div class="workspace-view">
              <div style="height: 3000px">tall form</div>
              <div class="dialog-overlay"><div class="dialog-card">sure?</div></div>
            </div>
          </section>
        </div>
      `);

      const overlay = await page.locator(".dialog-overlay").boundingBox();
      const pane = await page.locator(".workspace").boundingBox();
      assert.ok(overlay && pane);
      // Guard the guard: if the pane ever matched the viewport, this test
      // would pass without proving anything.
      assert.ok(
        pane.width < 900,
        `the pane must be narrower than the viewport to prove anything (got ${pane.width})`,
      );

      assert.equal(
        Math.round(overlay.width),
        900,
        "overlay is sized to the pane, so an ancestor still captures it",
      );
      assert.equal(Math.round(overlay.height), 600);
      assert.equal(Math.round(overlay.y), 0);
    } finally {
      await browser.close();
    }
  },
);


test("the diagnostics chips separate blockers from optional rows", () => {
  const source = read("../components/ResourceManager.tsx");
  const css = readStylesheet();

  // The backend sends `blocking_resources` and an `optional` flag; painting
  // every unusable row red is what told users to install tools they had no use
  // for, under a heading that promised those rows blocked the task.
  assert.match(source, /diagnostics\.blocking_resources\.includes/);
  assert.match(source, /is-advisory/);
  assert.match(css, /\.resource-label\.is-advisory\s*\{/);
});


test("the weights notice follows the real model state", () => {
  const page = read("../app/page.tsx");
  const newTask = read("../components/NewTask.tsx");
  const processing = read("../components/ProcessingView.tsx");

  // The task page claimed "about 3.4 GB" while the resources page said the
  // weights were ready. Both views now take the answer from the resource row.
  assert.match(page, /pipelineModelsReady\(state\.resources\)/);
  assert.match(newTask, /modelsReady\s*\?\s*t\.newTask\.firstRunNoticeWarm/);
  assert.match(processing, /modelsReady\s*\?\s*t\.newTask\.firstRunNoticeWarm/);
});

test("pipelineModelsReady says no when the row is absent", () => {
  // A payload that has not resolved the models row must not be read as "the
  // weights are here" -- that would suppress a download the user does face.
  assert.equal(pipelineModelsReady([]), false);
  assert.equal(
    pipelineModelsReady([
      { id: "models", version: "on-demand", state: "missing", optional: true },
    ]),
    false,
  );
  assert.equal(
    pipelineModelsReady([
      { id: "models", version: "on-demand", state: "ready", optional: true },
    ]),
    true,
  );
  // "outdated" is installed and usable: isUsable's whole point.
  assert.equal(
    pipelineModelsReady([
      { id: "models", version: "on-demand", state: "outdated", optional: true },
    ]),
    true,
  );
});


test("the diagnostics payload carries the model locations actually in use", () => {
  const service = read("../../backend/resources/desktop_service.py");

  // `paths.models` is what the UI can move and purge, but the pipeline prefers
  // the conventional per-user cache when it already holds the weights. Showing
  // only the managed path made both actions look like they covered GB that
  // were never in it.
  assert.match(service, /"model_locations": self\._model_locations\(\)/);
  assert.match(service, /existing_hf_home\(/);
  assert.match(service, /existing_separator_dir\(/);
});

test("the LLM panel re-reads keys written from outside the app", () => {
  const page = read("../app/page.tsx");
  const bridge = read("../lib/bridge.ts");

  // The data root is shared with the CLI on purpose, but the payload the
  // window renders was snapshotted at start-up, so a copied-in `.env` needed a
  // restart. Both halves are needed: a bridge method nothing calls changes
  // nothing.
  assert.match(bridge, /reload_settings/);
  assert.match(page, /reloadSettings\(\)/);
  assert.match(page, /addEventListener\("focus"/);
});


test("every output stage the dropdown offers is one the pipeline has", () => {
  const taskSettings = read("../components/TaskSettings.tsx");
  const types = read("../lib/types.ts");

  // `translated-srt` is the LLM pass without the re-wrap post-processing that
  // `final-srt` adds. Offering only the two ends also hid the byproduct users
  // were being told to fetch by hand.
  const stageUnion = types.match(/export type PipelineStage =([\s\S]*?);/)?.[1];
  assert.ok(stageUnion);
  for (const stage of ["raw-srt", "translated-srt", "final-srt"]) {
    assert.ok(stageUnion.includes(`"${stage}"`), `${stage} left the union`);
    assert.ok(
      taskSettings.includes(`value: "${stage}"`),
      `${stage} is not offered by the dropdown`,
    );
  }
});


test("a finished task leaves the workspace when the sidebar navigates", () => {
  const page = read("../app/page.tsx");

  // The completion card used to be pinned regardless of route, so the sidebar
  // "新建任务" entry looked dead: two controls with the same name did
  // different things.
  assert.match(
    page,
    /state\.task\.phase === "completed" && state\.route === "new-task"/,
  );
});
