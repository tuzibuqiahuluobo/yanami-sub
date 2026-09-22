"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { BatchQueue } from "@/components/BatchQueue";
import { BootstrapScreen } from "@/components/BootstrapScreen";
import { CompletedView } from "@/components/CompletedView";
import { ConfirmDialog, isConfirmRemembered } from "@/components/ConfirmDialog";
import { KnowledgeCenter } from "@/components/KnowledgeCenter";
import { LanguageProvider, useLanguage } from "@/components/LanguageProvider";
import { NewTask } from "@/components/NewTask";
import { ProcessingView } from "@/components/ProcessingView";
import { ResourceManager } from "@/components/ResourceManager";
import { Settings } from "@/components/Settings";
import { TaskHistory } from "@/components/TaskHistory";
import { ToastProvider, ToastViewport, useToast } from "@/components/ToastProvider";
import { UpdateAnnouncement } from "@/components/UpdateAnnouncement";
import {
  BridgeCallError,
  desktopApi,
} from "@/lib/bridge";
import {
  hydratePreferences,
  saveTaskDefaults,
  saveUi,
  uiValue,
} from "@/lib/preferences";
import {
  readProcessingDevice,
  requestDeviceFields,
} from "@/lib/processingDevice";
import { blockingResources, hasActiveInstall, pipelineModelsReady } from "@/lib/resources";
import {
  REMEMBERED_TASK_FIELDS,
  initialState,
  reduceAppState,
} from "@/lib/state";
import type {
  ApiProvider,
  BridgeError,
  Route,
  RoutingUpdate,
  TaskRequest,
  UpdateCheck,
  UpdateInstallSnapshot,
} from "@/lib/types";
import { useAppearance } from "@/lib/useAppearance";


function rememberTaskOptions(changes: Partial<Omit<TaskRequest, "input">>): void {
  const patch: Record<string, unknown> = {};
  for (const field of REMEMBERED_TASK_FIELDS) {
    if (field in changes) patch[field] = changes[field];
  }
  if (Object.keys(patch).length > 0) {
    saveTaskDefaults(patch);
  }
}


function toBridgeError(error: unknown): BridgeError {
  if (error instanceof BridgeCallError) {
    return {
      code: error.code,
      message: error.message,
      action: error.action,
    };
  }
  return {
    code: "internal_error",
    message: error instanceof Error ? error.message : "操作失败，请稍后重试。",
  };
}

/** Not a backend failure: the workspace has to leave "checking" before the
 *  resource page takes over, or it sits on a spinner with no task behind it. */
const RESOURCE_REQUIRED_ERROR: BridgeError = {
  code: "runtime_required",
  message: "还缺少运行所需的组件，正在为你安装。",
  action: "open_resources",
};


export default function Home() {
  return (
    <LanguageProvider>
      <ToastProvider>
        <HomeContent />
      </ToastProvider>
    </LanguageProvider>
  );
}


function HomeContent() {
  const [state, dispatch] = useReducer(reduceAppState, initialState);
  const [busy, setBusy] = useState(false);
  const [bootstrapError, setBootstrapError] = useState<BridgeError | null>(null);
  const eventCursor = useRef(0);
  const { t } = useLanguage();
  const { showSuccess } = useToast();
  const { settings: appearance, update: updateAppearance } = useAppearance();
  const [confirmOpen, setConfirmOpen] = useState(false);
  // Which task the cleanup dialog is asking about; null when it is closed.
  const [cleanupTaskId, setCleanupTaskId] = useState<string | null>(null);
  const [startupUpdate, setStartupUpdate] = useState<UpdateCheck | null>(null);
  const [dismissedUpdateVersion, setDismissedUpdateVersion] = useState("");
  const [autoUpdateCheck, setAutoUpdateCheck] = useState(
    () => uiValue<boolean>("autoUpdateCheck", true),
  );
  const [updateInstall, setUpdateInstall] = useState<UpdateInstallSnapshot | null>(null);

  const pollUpdateInstall = useCallback(async () => {
    try {
      const snapshot = await desktopApi.getUpdateInstall();
      setUpdateInstall((current) =>
        snapshot === null &&
        (current?.state === "queued" || current?.state === "running")
          ? current
          : snapshot,
      );
    } catch {
      // Keep the last useful progress through a transient bridge failure.
    }
  }, []);

  const startUpdateInstall = useCallback(
    async (kind: "app" | "full", version: string) => {
      const snapshot = await desktopApi.installUpdate(kind, version);
      setUpdateInstall(snapshot);
      return snapshot;
    },
    [],
  );

  const updateInstallActive =
    updateInstall?.state === "queued" || updateInstall?.state === "running";

  useEffect(() => {
    void pollUpdateInstall();
  }, [pollUpdateInstall]);

  useEffect(() => {
    if (!updateInstallActive) return;
    const timer = window.setInterval(() => void pollUpdateInstall(), 500);
    return () => window.clearInterval(timer);
  }, [pollUpdateInstall, updateInstallActive]);

  const changeAutoUpdateCheck = useCallback((enabled: boolean) => {
    setAutoUpdateCheck(enabled);
    saveUi({ autoUpdateCheck: enabled });
  }, []);

  const dismissUpdateAnnouncement = useCallback(() => {
    if (startupUpdate) setDismissedUpdateVersion(startupUpdate.version);
  }, [startupUpdate]);

  const disableUpdateAnnouncements = useCallback(() => {
    changeAutoUpdateCheck(false);
    if (startupUpdate) setDismissedUpdateVersion(startupUpdate.version);
  }, [changeAutoUpdateCheck, startupUpdate]);

  const installAnnouncedUpdate = useCallback(async () => {
    if (!startupUpdate?.kind) return;
    await startUpdateInstall(startupUpdate.kind, startupUpdate.version);
    setDismissedUpdateVersion(startupUpdate.version);
    dispatch({ type: "navigate", route: "settings" });
  }, [startupUpdate, startUpdateInstall]);

  const openAnnouncedUpdatePage = useCallback(
    () => desktopApi.openUpdatePage(),
    [],
  );

  // One release-feed query per launch, when the user leaves it on. Held here
  // rather than in the settings page so the sidebar can point at it: a check
  // nobody is told about is the same as no check. Fired from `loadBootstrap`
  // rather than its own mount effect so the preference is read *after*
  // hydration -- settings.json is the record, and a mount-time read would ask
  // the localStorage mirror instead. The ref makes "one per launch" literal:
  // a retried bootstrap goes through here again, and dev StrictMode would
  // otherwise double the request.
  const startupCheckFired = useRef(false);
  const maybeCheckForUpdates = useCallback(() => {
    if (startupCheckFired.current || !uiValue("autoUpdateCheck", true)) {
      return;
    }
    startupCheckFired.current = true;
    void (async () => {
      try {
        const result = await desktopApi.checkUpdates();
        if (result.available) {
          setStartupUpdate(result);
        }
      } catch {
        // No release source, no network, a rate limit: none of that is worth
        // an error on a screen the user did not ask anything of.
      }
    })();
  }, []);

  const loadBootstrap = useCallback(async () => {
    setBootstrapError(null);
    try {
      const payload = await desktopApi.getBootstrapState();
      // Before the dispatch: the theme and language readers are synchronous
      // and would otherwise render one frame from the mirror.
      hydratePreferences(payload.preferences);
      setAutoUpdateCheck(uiValue<boolean>("autoUpdateCheck", true));
      dispatch({ type: "bootstrapLoaded", payload });
      maybeCheckForUpdates();
    } catch (error) {
      setBootstrapError(toBridgeError(error));
    }
  }, [maybeCheckForUpdates]);

  useEffect(() => {
    void loadBootstrap();
  }, [loadBootstrap]);

  // `%LOCALAPPDATA%\FineSub\user-data` is shared with the CLI on purpose, so a
  // key can appear from outside this application -- a CLI run, another front
  // end, or a `.env` the user copied in. Every read backend-side goes to the
  // file, but the payload this window renders was snapshotted at start-up, so
  // the answer used to need a restart. Re-reading when the window regains focus
  // is the moment such a change becomes real for the user.
  useEffect(() => {
    const onFocus = () => {
      void (async () => {
        try {
          const refreshed = await desktopApi.reloadSettings();
          dispatch({ type: "settingsChanged", settings: refreshed.settings });
        } catch {
          // A refresh nobody asked for must not raise an error banner.
        }
      })();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  useEffect(() => {
    if (state.task.phase !== "running" || !state.task.taskId) {
      eventCursor.current = 0;
      return;
    }
    let stopped = false;
    // Without this, a poll slower than the 700ms interval overlaps the next
    // one: two responses land out of order, the older `nextCursor` wins, and
    // the drawer replays log lines it already showed.
    let inFlight = false;
    const poll = async () => {
      if (inFlight) {
        return;
      }
      inFlight = true;
      try {
        const result = await desktopApi.pollEvents(eventCursor.current);
        if (stopped) {
          return;
        }
        for (const event of result.events) {
          dispatch({ type: "workerEvent", event });
        }
        eventCursor.current = result.nextCursor;
      } catch {
        // A transient bridge poll failure must not destroy task state. A
        // permanent one is indistinguishable from here, which is why the
        // worker also writes task-log.txt beside the outputs.
      } finally {
        inFlight = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 700);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [state.task.phase, state.task.taskId]);

  useEffect(() => {
    if (!state.bootstrapped) {
      return;
    }
    let stopped = false;
    let inFlight = false;
    const syncHistory = async () => {
      if (inFlight) {
        return;
      }
      inFlight = true;
      try {
        const tasks = await desktopApi.listTasks();
        if (!stopped) {
          dispatch({ type: "tasksLoaded", tasks });
        }
      } catch {
        // History is durable on disk; a transient refresh failure should not
        // clear the rows already visible in the interface.
      } finally {
        inFlight = false;
      }
    };
    void syncHistory();
    const timer = window.setInterval(
      () => void syncHistory(),
      document.hidden ? 5000 : 2000,
    );
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [state.bootstrapped]);

  const hasActiveResourceInstall = hasActiveInstall(state.resourceInstalls);

  useEffect(() => {
    if (
      !state.bootstrapped ||
      (!hasActiveResourceInstall && state.route !== "resources")
    ) {
      return;
    }
    let stopped = false;
    const poll = async () => {
      try {
        const [installs, resources] = await Promise.all([
          desktopApi.listResourceInstalls(),
          desktopApi.getResourceStatuses(),
        ]);
        if (!stopped) {
          dispatch({ type: "resourceInstallsChanged", installs });
          dispatch({ type: "resourcesLoaded", resources });
        }
      } catch {
        // Keep the last known progress during a transient bridge failure.
      }
    };
    void poll();
    const timer = window.setInterval(
      () => void poll(),
      document.hidden ? 1500 : 500,
    );
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [hasActiveResourceInstall, state.bootstrapped, state.route]);

  const completedTaskToasts = useRef(new Set<string>());
  useEffect(() => {
    if (
      state.task.phase !== "completed" ||
      !state.task.taskId ||
      completedTaskToasts.current.has(state.task.taskId)
    ) {
      return;
    }
    completedTaskToasts.current.add(state.task.taskId);
    showSuccess(t.toast.taskCompleted, `task-completed-${state.task.taskId}`);
  }, [showSuccess, state.task.phase, state.task.taskId, t.toast.taskCompleted]);

  const previousResourceStates = useRef<Map<string, string> | null>(null);
  useEffect(() => {
    const next = new Map(state.resources.map((resource) => [resource.id, resource.state]));
    const previous = previousResourceStates.current;
    if (previous) {
      for (const resource of state.resources) {
        if (resource.state === "ready" && previous.get(resource.id) === "downloading") {
          showSuccess(
            t.toast.resourceInstalled.replace("{name}", resource.id),
            `resource-ready-${resource.id}-${resource.version}`,
          );
        }
      }
    }
    previousResourceStates.current = next;
  }, [showSuccess, state.resources, t.toast.resourceInstalled]);

  const selectFile = async () => {
    try {
      const result = await desktopApi.selectInputFile();
      if (result.path) {
        dispatch({ type: "fileSelected", path: result.path });
      }
    } catch (error) {
      dispatch({ type: "taskRejected", error: toBridgeError(error) });
    }
  };

  const installResource = async (resourceId: string) => {
    const current = state.resources.find((resource) => resource.id === resourceId);
    if (!current) {
      return;
    }
    dispatch({
      type: "resourceChanged",
      resource: { ...current, state: "downloading", detail: "" },
    });
    try {
      const install = await desktopApi.installResource(resourceId);
      dispatch({ type: "resourceInstallChanged", install });
      const resources = await desktopApi.getResourceStatuses();
      dispatch({ type: "resourcesLoaded", resources });
    } catch (error) {
      dispatch({
        type: "resourceChanged",
        resource: {
          ...current,
          state: "failed",
          detail: toBridgeError(error).message,
        },
      });
    }
  };

  const pauseResource = async (resourceId: string) => {
    try {
      const install = await desktopApi.pauseResourceInstall(resourceId);
      dispatch({ type: "resourceInstallChanged", install });
    } catch (error) {
      const current = state.resources.find(
        (resource) => resource.id === resourceId,
      );
      if (current) {
        dispatch({
          type: "resourceChanged",
          resource: {
            ...current,
            state: "failed",
            detail: toBridgeError(error).message,
          },
        });
      }
    }
  };

  const startTask = async () => {
    if (!state.task.selectedFile) {
      return;
    }
    if (!isConfirmRemembered("start-task")) {
      setConfirmOpen(true);
      return;
    }
    await executeStartTask();
  };

  const executeStartTask = async () => {
    if (!state.task.selectedFile) {
      return;
    }
    setBusy(true);
    dispatch({ type: "taskChecking" });
    try {
      // Only what a task genuinely needs. `yt-dlp` has no system-tool finder
      // by design, so it is permanently "missing" on a healthy machine; gating
      // on it meant no task could ever start until both on-demand tools were
      // installed, which is exactly what marking them optional prevents.
      const [missing] = blockingResources(state.resources);
      if (missing) {
        // Leave "checking" before handing off, or the workspace sits on a
        // spinner with no task behind it.
        dispatch({ type: "taskRejected", error: RESOURCE_REQUIRED_ERROR });
        dispatch({ type: "navigate", route: "resources" });
        await installResource(missing.id);
        return;
      }
      // The processing device is one global setting, not a per-task control,
      // but it has to ride along with the request: that is the only thing the
      // backend receives, and it is what retry and resume replay later.
      const processing = readProcessingDevice();
      const snapshot = await desktopApi.startTask({
        input: state.task.selectedFile,
        ...state.task.request,
        ...requestDeviceFields(processing),
      });
      dispatch({ type: "taskStarted", snapshot });
    } catch (error) {
      const bridgeError = toBridgeError(error);
      dispatch({ type: "taskRejected", error: bridgeError });
      if (bridgeError.action === "show_batch") {
        dispatch({ type: "navigate", route: "batch" });
      }
    } finally {
      setBusy(false);
    }
  };

  const cancelTask = async () => {
    if (!state.task.taskId) {
      return;
    }
    try {
      await desktopApi.cancelTask(state.task.taskId);
      dispatch({
        type: "workerEvent",
        event: {
          type: "cancelled",
          task_id: state.task.taskId,
          timestamp: new Date().toISOString(),
          payload: {},
        },
      });
    } catch (error) {
      dispatch({ type: "taskRejected", error: toBridgeError(error) });
    }
  };

  const restartHistoryTask = async (
    taskId: string,
    mode: "retry" | "resume",
  ) => {
    setBusy(true);
    try {
      const snapshot =
        mode === "resume"
          ? await desktopApi.resumeTask(taskId)
          : await desktopApi.retryTask(taskId);
      dispatch({ type: "taskStarted", snapshot });
    } catch (error) {
      dispatch({ type: "taskRejected", error: toBridgeError(error) });
    } finally {
      setBusy(false);
    }
  };

  const deleteIntermediates = async (taskId: string) => {
    try {
      await desktopApi.deleteTaskIntermediates(taskId);
    } catch (error) {
      dispatch({ type: "taskRejected", error: toBridgeError(error) });
    } finally {
      setCleanupTaskId(null);
    }
  };

  const cancelHistoryTask = async (taskId: string) => {
    try {
      await desktopApi.cancelTask(taskId);
      dispatch({
        type: "workerEvent",
        event: {
          type: "cancelled",
          task_id: taskId,
          timestamp: new Date().toISOString(),
          payload: {},
        },
      });
    } catch (error) {
      dispatch({ type: "taskRejected", error: toBridgeError(error) });
    }
  };

  const saveKey = async (
    provider: ApiProvider,
    value: string,
  ) => {
    const settings = await desktopApi.saveApiKeys({ [provider]: value });
    dispatch({ type: "settingsChanged", settings });
    dispatch({ type: "routingChanged", routing: await desktopApi.getRoutingSettings() });
  };

  const deleteKey = async (provider: ApiProvider) => {
    const settings = await desktopApi.deleteApiKey(provider);
    dispatch({ type: "settingsChanged", settings });
    dispatch({ type: "routingChanged", routing: await desktopApi.getRoutingSettings() });
  };



  let content;
  if (state.route === "batch") {
    content = (
      <BatchQueue
        request={state.task.request}
        capabilities={state.capabilities}
        routing={state.routing}
        onRequestChange={(changes) => {
          dispatch({ type: "requestChanged", changes });
          rememberTaskOptions(changes);
        }}
        onOpenResources={() => dispatch({ type: "navigate", route: "resources" })}
      />
    );
  } else if (state.route === "history") {
    content = (
      <TaskHistory
        tasks={state.history}
        reuseDisabled={
          busy ||
          state.task.phase === "running" ||
          state.task.phase === "checking"
        }
        onCancel={(taskId) => void cancelHistoryTask(taskId)}
        onRetry={(taskId) => void restartHistoryTask(taskId, "retry")}
        onResume={(taskId) => void restartHistoryTask(taskId, "resume")}
        onReuse={(snapshot) => dispatch({ type: "reuseAsr", snapshot })}
        onOpenOutput={(path) => void desktopApi.openOutput(path)}
        onOpenTasksDirectory={() => void desktopApi.openTasksDirectory()}
        onDeleteIntermediates={(taskId) => {
          if (isConfirmRemembered("delete-intermediates")) {
            void deleteIntermediates(taskId);
            return;
          }
          setCleanupTaskId(taskId);
        }}
      />
    );
  } else if (state.route === "knowledge") {
    content = <KnowledgeCenter tasks={state.history} />;
  } else if (state.route === "resources") {
    content = (
      <ResourceManager
        resources={state.resources}
        installs={state.resourceInstalls}
        onInstall={(resourceId) => void installResource(resourceId)}
        onPause={(resourceId) => void pauseResource(resourceId)}
        onOpenLocation={(resourceId, kind) =>
          void desktopApi.openResourceLocation(resourceId, kind)
        }
        onOpenLogs={() => void desktopApi.openInstallLogs()}
        onRunDiagnostics={() => desktopApi.getDiagnostics()}
        onCheckPythonInterpreter={() => desktopApi.getPythonInterpreter()}
        onSelectPythonInterpreter={() => desktopApi.selectPythonInterpreter()}
        onClearPythonInterpreter={() => desktopApi.clearPythonInterpreter()}
        storage={state.storage}
        onRelocateData={async (reset) => {
          const result = await desktopApi.relocateData(reset);
          if (!result.cancelled) await loadBootstrap();
          return result;
        }}
        onPurgeRebuildableData={async () => {
          const result = await desktopApi.purgeRebuildableData(
            "PURGE_REBUILDABLE_DATA",
          );
          await loadBootstrap();
          return result;
        }}
      />
    );
  } else if (state.route === "settings") {
    content = (
      <Settings
        state={state}
        appearance={appearance}
        onAppearanceChange={updateAppearance}
        onSaveKey={saveKey}
        onDeleteKey={deleteKey}
        onRevealKeys={() => desktopApi.revealApiKeys()}
        onExportKeys={() => desktopApi.exportApiKeys()}
        onSaveRouting={async (values: RoutingUpdate) => {
          const routing = await desktopApi.saveRoutingSettings(values);
          dispatch({ type: "routingChanged", routing });
        }}
        onSaveProviderKey={async (providerId, value) => {
          const routing = await desktopApi.saveProviderKey(providerId, value);
          dispatch({ type: "routingChanged", routing });
        }}
        onDeleteProviderKey={async (providerId) => {
          const routing = await desktopApi.deleteProviderKey(providerId);
          dispatch({ type: "routingChanged", routing });
        }}
        onProbeLocalAgents={() => desktopApi.probeLocalAgents()}
        onUseRawSubtitle={() => {
          dispatch({
            type: "requestChanged",
            changes: { stage: "raw-srt" },
          });
          dispatch({ type: "navigate", route: "new-task" });
        }}
        startupUpdate={startupUpdate}
        onCheckUpdates={() => desktopApi.checkUpdates()}
        updateInstall={updateInstall}
        onInstallUpdate={startUpdateInstall}
        onCloseWindow={() => desktopApi.closeWindow()}
        onRestartApplication={() => desktopApi.restartApplication()}
        onOpenUpdatePage={() => desktopApi.openUpdatePage()}
        autoCheck={autoUpdateCheck}
        onAutoCheckChange={changeAutoUpdateCheck}
        onRescanGpus={() => desktopApi.rescanGpus()}
        onSaveSharedSettings={async (values) => {
          const result = await desktopApi.saveSharedSettings(values);
          dispatch({
            type: "sharedSettingsChanged",
            settings: result.shared,
            configPath: result.config_path,
          });
        }}
      />
    );
  } else if (
    state.task.phase === "running" ||
    // A failed task keeps the workspace only while the user is looking at
    // it. Pinning the view regardless of route left "新建任务" rendering the
    // same error screen from every page, with no drop zone and no way out
    // but retrying the file that just failed.
    (state.task.phase === "failed" && state.route === "new-task")
  ) {
    content = (
      <ProcessingView
        task={state.task}
        firstRun={
          !state.history.some((snapshot) => snapshot.state === "completed")
        }
        modelsReady={pipelineModelsReady(state.resources)}
        onCancel={() => void cancelTask()}
        onRetry={() => void startTask()}
      />
    );
  } else if (
    state.task.phase === "completed" && state.route === "new-task"
  ) {
    content = (
      <CompletedView
        task={state.task}
        onOpen={(path) => void desktopApi.openOutput(path)}
        onReset={() => dispatch({ type: "resetTask" })}
      />
    );
  } else {
    content = (
      <NewTask
        state={state}
        busy={busy}
        modelsReady={pipelineModelsReady(state.resources)}
        onSelectFile={() => void selectFile()}
        onDropPath={(path) => dispatch({ type: "fileSelected", path })}
        onRequestChange={(changes: Partial<Omit<TaskRequest, "input">>) => {
          dispatch({ type: "requestChanged", changes });
          rememberTaskOptions(changes);
        }}
        onReuse={(snapshot) => dispatch({ type: "reuseAsr", snapshot })}
        onInstallResource={(resourceId) => void installResource(resourceId)}
        onOpenResources={() =>
          dispatch({ type: "navigate", route: "resources" })
        }
        onStart={() => void startTask()}
      />
    );
  }

  return (
    <>
      {!state.bootstrapped ? (
        <BootstrapScreen error={bootstrapError} onRetry={loadBootstrap} />
      ) : (
        <AppShell
          state={state}
          api={desktopApi}
          onNavigate={(route: Route) => dispatch({ type: "navigate", route })}
          updateAvailable={startupUpdate?.available === true}
        >
          {content}
          <StartTaskConfirmDialog
            open={confirmOpen}
            onConfirm={() => {
              setConfirmOpen(false);
              void executeStartTask();
            }}
            onCancel={() => setConfirmOpen(false)}
          />
          <DeleteIntermediatesConfirmDialog
            open={cleanupTaskId !== null}
            onConfirm={() => {
              if (cleanupTaskId !== null) {
                void deleteIntermediates(cleanupTaskId);
              }
            }}
            onCancel={() => setCleanupTaskId(null)}
          />
          <UpdateAnnouncement
            open={
              startupUpdate?.available === true &&
              dismissedUpdateVersion !== startupUpdate.version
            }
            update={startupUpdate}
            onClose={dismissUpdateAnnouncement}
            onDisableAnnouncements={disableUpdateAnnouncements}
            onInstall={installAnnouncedUpdate}
            onOpenUpdatePage={openAnnouncedUpdatePage}
          />
        </AppShell>
      )}
      <ToastViewport updateInstall={updateInstall} />
    </>
  );
}

function DeleteIntermediatesConfirmDialog({
  open,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useLanguage();

  return (
    <ConfirmDialog
      config={{
        id: "delete-intermediates",
        title: t.history.deleteIntermediatesConfirmTitle,
        message: t.history.deleteIntermediatesConfirmBody,
        confirmLabel: t.history.deleteIntermediatesConfirmAction,
      }}
      open={open}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}

function StartTaskConfirmDialog({
  open,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useLanguage();

  return (
    <ConfirmDialog
      config={{
        id: "start-task",
        title: t.startTaskConfirm.title,
        message: t.startTaskConfirm.message,
        confirmLabel: t.startTaskConfirm.confirm,
        cancelLabel: t.startTaskConfirm.cancel,
      }}
      open={open}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
