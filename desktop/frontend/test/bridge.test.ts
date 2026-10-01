import assert from "node:assert/strict";
import test from "node:test";

import {
  BridgeCallError,
  createDesktopApi,
  unwrapEnvelope,
} from "../lib/bridge";


test("error envelopes preserve bridge code and action", () => {
  assert.throws(
    () =>
      unwrapEnvelope({
        ok: false,
        error: {
          code: "api_key_required",
          message: "missing",
          action: "open_settings",
        },
      }),
    (error: unknown) =>
      error instanceof BridgeCallError &&
      error.code === "api_key_required" &&
      error.action === "open_settings",
  );
});


test("browser preview fallback is deterministic", async () => {
  const api = createDesktopApi({ preview: true });

  const first = await api.getBootstrapState();
  const second = await api.getBootstrapState();

  assert.deepEqual(first, second);
  assert.equal(first.capabilities.translation, false);
  assert.equal(first.resources[0]?.state, "ready");
});


test("browser preview exposes update check and release page", async () => {
  const api = createDesktopApi({ preview: true });

  const check = await api.checkUpdates();
  const release = await api.openUpdatePage();

  // The preview reports a release on purpose: the sidebar dot, the notes and
  // the install button have no other way to appear in the browser.
  assert.equal(check.available, true);
  assert.equal(check.kind, "app");
  assert.ok(check.releaseNotes);
  assert.deepEqual(release, {
    url: "https://github.com/tuzibuqiahuluobo/yanami-sub/releases",
  });
});


test("browser preview exposes the batch scheduler contract", async () => {
  const api = createDesktopApi({ preview: true });
  const bootstrap = await api.getBootstrapState();
  const template = bootstrap.tasks?.[0]?.request;
  assert.ok(template);
  const selected = await api.selectBatchFiles();

  const started = await api.startBatch({
    items: selected.paths.map((input, index) => ({
      ...template,
      input,
      group: "",
      priority: selected.paths.length - index,
    })),
    workers: { download: 2, asr: 1, llm: 2 },
    asr_queue_size: 4,
    retry_failed: 1,
  });

  assert.equal(started.state, "running");
  assert.equal(started.items.length, 2);
  assert.equal((await api.getBatchSnapshot())?.batch_id, started.batch_id);
  assert.equal((await api.listBatches()).length, 1);
});

test("browser preview keeps custom Agent paths separate by tier", async () => {
  const api = createDesktopApi({ preview: true });
  assert.equal((await api.getAgentPaths()).paths.LOCAL_DSH, "");
  await api.setAgentPath("LOCAL_DSH", "G:/deepseek-harness");
  await api.setAgentPath("LOCAL_CLAUDE", "G:/claude-code/cli.js");
  const paths = (await api.getAgentPaths()).paths;
  assert.equal(paths.LOCAL_DSH, "G:/deepseek-harness");
  assert.equal(paths.LOCAL_CLAUDE, "G:/claude-code/cli.js");
  assert.equal(paths.LOCAL_CODEX, "");
});

test("browser preview cancels native Agent selection without changing paths", async () => {
  const api = createDesktopApi({ preview: true });
  await api.setAgentPath("LOCAL_CODEX", "D:/Agent/codex.exe");
  assert.deepEqual(await api.selectAgentPath("LOCAL_CODEX", "file"), { cancelled: true });
  assert.deepEqual(await api.selectAgentPath("LOCAL_CODEX", "directory"), { cancelled: true });
  assert.equal((await api.getAgentPaths()).paths.LOCAL_CODEX, "D:/Agent/codex.exe");
});

test("Agent path picker forwards tier and file/directory kind to native bridge", async () => {
  const previousWindow = globalThis.window;
  const calls: unknown[][] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { search: "" },
      pywebview: { api: { select_agent_path: async (...args: unknown[]) => {
        calls.push(args);
        return { ok: true, data: { cancelled: false, path: "D:/Agent/codex.exe" } };
      } } },
    },
  });
  try {
    const api = createDesktopApi({ preview: false });
    assert.equal((await api.selectAgentPath("LOCAL_CODEX", "file")).path, "D:/Agent/codex.exe");
    await api.selectAgentPath("LOCAL_WORKBUDDY", "directory");
    assert.deepEqual(calls, [["LOCAL_CODEX", "file"], ["LOCAL_WORKBUDDY", "directory"]]);
  } finally {
    if (previousWindow === undefined) Reflect.deleteProperty(globalThis, "window");
    else Object.defineProperty(globalThis, "window", { configurable: true, value: previousWindow });
  }
});


test("browser preview round-trips a static batch manifest", async () => {
  const api = createDesktopApi({ preview: true });

  const imported = await api.importBatchManifest();
  assert.ok(imported.request);
  const exported = await api.exportBatchManifest(imported.request);

  assert.equal(imported.request.items.length, 1);
  assert.equal(exported.count, 1);
  assert.equal(exported.path, "D:/Media/finesub-batch.jsonl");
});


test("browser preview exposes the knowledge workspace contract", async () => {
  const api = createDesktopApi({ preview: true });

  const snapshot = await api.getKnowledgeSnapshot();
  const entry = await api.getKnowledgeEntry("common/FineSub");
  const feedback = await api.getTaskKnowledgeFeedback("preview-task");
  const maintenance = await api.runKnowledgeMaintenance({
    command: "verify",
    args: [],
    content: "",
  });

  assert.equal(snapshot.revision, 12);
  assert.equal(snapshot.entries[0]?.qualified_name, "common/FineSub");
  assert.equal(entry.text.includes("Yanami Sub"), true);
  assert.equal(feedback.merged_hints[0]?.entry, "FineSub");
  assert.equal(maintenance.command, "verify");
});


test("browser preview exposes key export and storage maintenance", async () => {
  const api = createDesktopApi({ preview: true });

  const exported = await api.exportApiKeys();
  const moved = await api.relocateData();
  const purged = await api.purgeRebuildableData("PURGE_REBUILDABLE_DATA");

  assert.equal(exported.cancelled, false);
  assert.equal(moved.storage.relocated, true);
  assert.equal(moved.storage.big_data, String.raw`D:\Yanami Sub Data`);
  assert.equal(purged.resources?.every((resource) => resource.state === "missing"), true);
});


test("desktop API uses the native Python bridge by default", async () => {
  const previousWindow = globalThis.window;
  const calls: string[] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { search: "" },
      pywebview: {
        api: {
          minimize_window: async () => {
            calls.push("minimize_window");
            return { ok: true, data: null };
          },
        },
      },
    },
  });

  try {
    await createDesktopApi().minimizeWindow();
    assert.deepEqual(calls, ["minimize_window"]);
  } finally {
    if (previousWindow === undefined) {
      Reflect.deleteProperty(globalThis, "window");
    } else {
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: previousWindow,
      });
    }
  }
});


test("desktop API exposes a distinct minimize-to-tray action", async () => {
  const previousWindow = globalThis.window;
  const calls: string[] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { search: "" },
      pywebview: {
        api: {
          minimize_to_tray: async () => {
            calls.push("minimize_to_tray");
            return { ok: true, data: null };
          },
        },
      },
    },
  });

  try {
    await createDesktopApi().minimizeToTray();
    assert.deepEqual(calls, ["minimize_to_tray"]);
  } finally {
    if (previousWindow === undefined) {
      Reflect.deleteProperty(globalThis, "window");
    } else {
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: previousWindow,
      });
    }
  }
});


test("desktop API exposes a real native restart action", async () => {
  const previousWindow = globalThis.window;
  const calls: string[] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { search: "" },
      pywebview: {
        api: {
          restart_application: async () => {
            calls.push("restart_application");
            return { ok: true, data: null };
          },
        },
      },
    },
  });

  try {
    await createDesktopApi().restartApplication();
    assert.deepEqual(calls, ["restart_application"]);
  } finally {
    if (previousWindow === undefined) {
      Reflect.deleteProperty(globalThis, "window");
    } else {
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: previousWindow,
      });
    }
  }
});


test("installUpdate forwards kind and version to the native bridge", async () => {
  const previousWindow = globalThis.window;
  const calls: unknown[][] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { search: "" },
      pywebview: {
        api: {
          install_update: async (...args: unknown[]) => {
            calls.push(args);
            return {
              ok: true,
              data: {
                version: "0.3.2",
                kind: "app",
                state: "queued",
                phase: "waiting",
                message: "",
                downloaded: 0,
                total: 0,
                bytes_per_second: 0,
                restart_required: false,
                exit_required: false,
                error: "",
                started_at: 0,
                updated_at: 0,
              },
            };
          },
          get_update_install: async () => ({ ok: true, data: null }),
        },
      },
    },
  });

  try {
    const api = createDesktopApi();
    const snapshot = await api.installUpdate("app", "0.3.2");
    const polled = await api.getUpdateInstall();

    // The backend re-derives the kind from the signed manifest and rejects a
    // mismatch, so what the page saw has to reach it verbatim.
    assert.deepEqual(calls, [["app", "0.3.2"]]);
    assert.equal(snapshot.state, "queued");
    assert.equal(polled, null);
  } finally {
    if (previousWindow === undefined) {
      Reflect.deleteProperty(globalThis, "window");
    } else {
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: previousWindow,
      });
    }
  }
});


test("GitHub feedback requests the default browser and allows retry after a launch failure", async () => {
  const previousWindow = globalThis.window;
  const calls: unknown[][] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { search: "" },
      pywebview: {
        api: {
          open_feedback_issue: async (...args: unknown[]) => {
            calls.push(args);
            return calls.length === 1
              ? { ok: false, error: { code: "invalid_request", message: "无法打开系统默认浏览器" } }
              : { ok: true, data: { url: "https://github.com/tuzibuqiahuluobo/yanami-sub/issues/new", opened: true } };
          },
        },
      },
    },
  });
  try {
    const api = createDesktopApi();
    await assert.rejects(() => api.openFeedbackIssue("中文 Bug", "Details"), /默认浏览器/);
    assert.equal((await api.openFeedbackIssue("中文 Bug", "Details")).opened, true);
    assert.deepEqual(calls, [["中文 Bug", "Details", true], ["中文 Bug", "Details", true]]);
  } finally {
    if (previousWindow === undefined) Reflect.deleteProperty(globalThis, "window");
    else Object.defineProperty(globalThis, "window", { configurable: true, value: previousWindow });
  }
});

test("browser preview refuses to install rather than pretending to", async () => {
  const api = createDesktopApi({ preview: true });

  assert.equal(await api.getUpdateInstall(), null);
  await assert.rejects(() => api.installUpdate("app", "0.3.2"));
});
