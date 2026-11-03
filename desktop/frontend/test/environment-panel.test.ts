import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { EnvironmentPanel } from "../components/EnvironmentPanel";
import type { ResourceInstallSnapshot, ResourceStatus } from "../lib/types";

const resource: ResourceStatus = { id: "uv", version: "1", state: "missing" };
const install: ResourceInstallSnapshot = {
  resource_id: "uv", resource_version: "1", state: "running", phase: "downloading",
  message: "下载中", downloaded: 42, total: 100, bytes_per_second: 1,
  cache_path: "", install_path: "", logs: [], error: "", started_at: 1, updated_at: 2,
};
const render = (resources: ResourceStatus[], installs: ResourceInstallSnapshot[], submitting: string[] = []) =>
  renderToStaticMarkup(createElement(EnvironmentPanel, { resources, installs, submitting, onInstall: () => {} }));

test("the resource action reflects waiting, progress, failure, pause and readiness", () => {
  const waiting = render([resource], [{ ...install, state: "failed", error: "old error" }], ["uv"]);
  assert.match(waiting, /lucide-loader-circle/);
  assert.doesNotMatch(waiting, /old error|environment-progress-value/);
  const running = render([resource], [install]);
  assert.match(running, /environment-progress-value/);
  assert.match(running, /42%/);
  const staleReady = render([{ ...resource, state: "ready" }], [install]);
  assert.match(staleReady, /environment-progress-value/);
  assert.doesNotMatch(staleReady, /已安装/);
  assert.match(staleReady.replace(/<!--.*?-->/g, ""), /0\/1/);
  const failed = render([resource], [{ ...install, state: "failed", error: "连接失败" }]);
  assert.match(failed, /连接失败/);
  assert.match(failed, /lucide-rotate-ccw/);
  const paused = render([resource], [{ ...install, state: "paused" }]);
  assert.match(paused, /已暂停/);
  assert.match(paused, /lucide-play/);
  const ready = render([{ ...resource, state: "ready" }], []);
  assert.match(ready, /已安装/);
  assert.doesNotMatch(ready, /lucide-download/);
});
