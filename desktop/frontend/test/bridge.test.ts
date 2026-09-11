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


test("browser preview refuses to install rather than pretending to", async () => {
  const api = createDesktopApi({ preview: true });

  assert.equal(await api.getUpdateInstall(), null);
  await assert.rejects(() => api.installUpdate("app", "0.3.2"));
});
