"use client";

import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Check,
  Download,
  FolderOpen,
  HardDrive,
  Info,
  LoaderCircle,
  Pause,
  Play,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { useRef, useState } from "react";

import { DownloadProgress } from "@/components/DownloadProgress";
import { RESOURCE_SIZES } from "@/lib/resourceCatalog";
import { isUsable, unresolvedDependency } from "@/lib/resources";
import type {
  DiagnosticsReport,
  PythonInterpreterChoice,
  ResourceInstallSnapshot,
  ResourceStatus,
  StorageMaintenanceResult,
  StorageState,
} from "@/lib/types";
import { useLanguage } from "./LanguageProvider";
import { useToast } from "./ToastProvider";


// 格式化字节大小
function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// 获取资源信息的辅助函数
function getResourceInfo(resourceId: string, t: any): { title: string; detail: string } {
  const known = t.resources.items[resourceId];
  if (known) {
    return { title: known.title, detail: known.detail };
  }
  return { title: resourceId, detail: t.resources.items.unknown.detail };
}


interface ResourceManagerProps {
  resources: ResourceStatus[];
  installs: ResourceInstallSnapshot[];
  onInstall: (resourceId: string) => void;
  onPause: (resourceId: string) => void;
  onOpenLocation: (
    resourceId: string,
    kind: "cache" | "install",
  ) => void;
  onOpenLogs: () => void;
  onRunDiagnostics: () => Promise<DiagnosticsReport>;
  onCheckPythonInterpreter: () => Promise<PythonInterpreterChoice>;
  onSelectPythonInterpreter: () => Promise<{
    cancelled?: boolean;
    path?: string;
    version?: string;
  }>;
  onClearPythonInterpreter: () => Promise<unknown>;
  storage: StorageState;
  onRelocateData: (reset: boolean) => Promise<StorageMaintenanceResult>;
  onPurgeRebuildableData: () => Promise<StorageMaintenanceResult>;
}


export function ResourceManager({
  resources,
  installs,
  onInstall,
  onPause,
  onOpenLocation,
  onOpenLogs,
  onRunDiagnostics,
  onCheckPythonInterpreter,
  onSelectPythonInterpreter,
  onClearPythonInterpreter,
  storage,
  onRelocateData,
  onPurgeRebuildableData,
}: ResourceManagerProps) {
  const { t } = useLanguage();
  const { showSuccess } = useToast();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingResourceId, setPendingResourceId] = useState<string | null>(null);
  const [pythonPreflight, setPythonPreflight] = useState<PythonInterpreterChoice | null>(null);
  const [pythonPreflightBusy, setPythonPreflightBusy] = useState(false);
  const [pythonPreflightError, setPythonPreflightError] = useState("");
  const pythonPreflightRequest = useRef(0);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsReport | null>(null);
  const [diagnosticError, setDiagnosticError] = useState("");
  const [pythonBusy, setPythonBusy] = useState<"" | "choose" | "clear">("");
  const [pythonNotice, setPythonNotice] = useState("");
  const [maintenanceBusy, setMaintenanceBusy] = useState<"move" | "reset" | "purge" | "">("");
  const [maintenanceError, setMaintenanceError] = useState("");
  const [maintenanceMessage, setMaintenanceMessage] = useState("");
  const [purgeConfirmOpen, setPurgeConfirmOpen] = useState(false);

  // 计算未安装资源的总大小
  // Only what a task actually waits on counts toward "space required"; the
  // on-demand tools are fetched when a run turns out to need them.
  const missingResources = resources.filter(
    (r) =>
      !r.optional &&
      // An upgrade is not a space requirement: the old copy already works, so
      // nothing is waiting on the user to free room for the new one.
      !isUsable(r) &&
      !installs.some((i) => i.resource_id === r.id && i.state === "ready")
  );
  const totalRequiredSpace = missingResources.reduce(
    (sum, r) => sum + (RESOURCE_SIZES[r.id] || 0),
    0
  );

  const closeInstallConfirm = () => {
    pythonPreflightRequest.current += 1;
    setConfirmOpen(false);
    setPendingResourceId(null);
    setPythonPreflightBusy(false);
  };

  const startPythonPreflight = () => {
    const requestId = ++pythonPreflightRequest.current;
    setPythonPreflight(null);
    setPythonPreflightError("");
    setPythonPreflightBusy(true);
    void onCheckPythonInterpreter()
      .then((result) => {
        if (pythonPreflightRequest.current === requestId) {
          setPythonPreflight(result);
        }
      })
      .catch((error) => {
        if (pythonPreflightRequest.current === requestId) {
          setPythonPreflightError(
            error instanceof Error
              ? error.message
              : t.resources.confirm.python.checkFailed,
          );
        }
      })
      .finally(() => {
        if (pythonPreflightRequest.current === requestId) {
          setPythonPreflightBusy(false);
        }
      });
  };

  const handleInstallClick = (resourceId: string) => {
    const resource = resources.find((r) => r.id === resourceId);
    const install = installs.find((i) => i.resource_id === resourceId);
    const isReady = resource?.state === "ready" || install?.state === "ready";
    const isRunning = install?.state === "queued" || install?.state === "running";

    if (isRunning) {
      onPause(resourceId);
    } else if (isReady) {
      onOpenLocation(resourceId, "install");
    } else {
      // 下载前显示确认对话框
      setPendingResourceId(resourceId);
      setConfirmOpen(true);
      setPythonPreflight(null);
      setPythonPreflightError("");
      if (resourceId === "uv") {
        startPythonPreflight();
      }
    }
  };

  const handleConfirmInstall = () => {
    if (pendingResourceId) {
      onInstall(pendingResourceId);
    }
    closeInstallConfirm();
  };

  const runDiagnostics = async () => {
    setDiagnosing(true);
    setDiagnosticError("");
    try {
      setDiagnostics(await onRunDiagnostics());
    } catch (error) {
      setDiagnosticError(
        error instanceof Error ? error.message : t.resources.diagnostics.failed,
      );
    } finally {
      setDiagnosing(false);
    }
  };

  const runPythonAction = async (kind: "choose" | "clear") => {
    let selected: {
      cancelled?: boolean;
      path?: string;
      version?: string;
    } | null = null;
    setPythonBusy(kind);
    setPythonNotice("");
    try {
      if (kind === "clear") {
        await onClearPythonInterpreter();
        setPythonNotice(t.resources.diagnostics.pythonCleared);
        showSuccess(t.resources.diagnostics.pythonCleared, "python-interpreter-cleared");
      } else {
        const result = await onSelectPythonInterpreter();
        if (!result?.cancelled) {
          setPythonNotice(t.resources.diagnostics.pythonRestart);
          showSuccess(t.resources.diagnostics.pythonRestart, "python-interpreter-saved");
          selected = result;
        }
      }
      if (diagnostics) {
        setDiagnostics(await onRunDiagnostics());
      }
    } catch (error) {
      setPythonNotice(
        error instanceof Error ? error.message : t.resources.diagnostics.failed,
      );
    } finally {
      setPythonBusy("");
    }
    return selected;
  };

  const choosePythonForInstall = async () => {
    setPythonPreflightError("");
    const result = await runPythonAction("choose");
    if (result?.path) {
      setPythonPreflight({
        configured: result.path,
        found: result.path,
        version: result.version ?? "3.12",
        detail: "",
        rejected: [],
      });
    }
  };

  const runStorageMaintenance = async (
    kind: "move" | "reset" | "purge",
  ) => {
    setMaintenanceBusy(kind);
    setMaintenanceError("");
    setMaintenanceMessage("");
    try {
      const result = kind === "purge"
        ? await onPurgeRebuildableData()
        : await onRelocateData(kind === "reset");
      if (!result.cancelled) {
        const message =
          kind === "purge"
            ? t.resources.storage.purged
            : kind === "reset"
              ? t.resources.storage.resetDone
              : t.resources.storage.moved;
        setMaintenanceMessage(message);
        showSuccess(message, `storage-maintenance-${kind}`);
      }
    } catch (error) {
      setMaintenanceError(
        error instanceof Error ? error.message : t.resources.storage.failed,
      );
    } finally {
      setMaintenanceBusy("");
      setPurgeConfirmOpen(false);
    }
  };

  const pendingResourceSize = pendingResourceId ? RESOURCE_SIZES[pendingResourceId] || 0 : 0;
  const pendingResourceInfo = pendingResourceId ? getResourceInfo(pendingResourceId, t) : null;
  const pythonConfirm = pendingResourceId === "uv";
  const pythonFound = pythonPreflight?.found ?? null;
  const interpreter = diagnostics?.python_interpreter;
  // Only worth stating when it disagrees with the managed path the row above
  // already shows.
  const modelsElsewhere = Boolean(
    diagnostics?.model_locations &&
      diagnostics.paths.models !== diagnostics.model_locations.hf_home,
  );

  return (
    <div className="page">
      <header className="page-header">
        <div>
          {/* <p className="page-kicker">{t.resources.kicker}</p> */}
          <h1>{t.resources.title}</h1>
          <p>{t.resources.description}</p>
        </div>
        <div className="page-header-actions">
          <button
            type="button"
            className="button button-secondary button-compact"
            disabled={diagnosing}
            onClick={() => void runDiagnostics()}
          >
            {diagnosing ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <Activity size={14} />
            )}
            {diagnosing
              ? t.resources.diagnostics.running
              : t.resources.diagnostics.action}
          </button>
          <button
            type="button"
            className="button button-secondary button-compact"
            onClick={onOpenLogs}
          >
            <FolderOpen size={14} />
            {t.resources.openLogs}
          </button>
        </div>
      </header>

      {/* 显示总磁盘空间需求 */}
      {missingResources.length > 0 && (
        <div className="resource-space-warning">
          <AlertTriangle size={16} />
          <div>
            <strong>{t.resources.spaceWarning.title}</strong>
            <p>
              {t.resources.spaceWarning.message.replace(
                "{size}",
                formatBytes(totalRequiredSpace),
              )}
            </p>
          </div>
        </div>
      )}

      <section className="diagnostics-card">
        <div className="diagnostics-heading">
          <div className="diagnostics-title">
            <span className={`resource-large-icon ${diagnostics?.healthy ? "is-ready" : ""}`}>
              {diagnostics?.healthy ? <Check size={20} /> : <Activity size={20} />}
            </span>
            <div>
              <strong>{t.resources.diagnostics.title}</strong>
              <p>
                {diagnostics
                  ? diagnostics.healthy
                    ? t.resources.diagnostics.healthy
                    : t.resources.diagnostics.needsAttention
                  : t.resources.diagnostics.description}
              </p>
            </div>
          </div>
          {diagnostics ? (
            <span className={`resource-label ${diagnostics.healthy ? "is-ready" : "is-failed"}`}>
              {diagnostics.healthy
                ? t.resources.diagnostics.passed
                : t.resources.diagnostics.failed}
            </span>
          ) : null}
        </div>

        {diagnosticError ? (
          <p className="resource-error">{diagnosticError}</p>
        ) : null}

        {diagnostics ? (
          <div className="diagnostics-result">
            <div className="diagnostics-meta">
              <span>
                <small>{t.resources.diagnostics.desktopVersion}</small>
                <strong>{diagnostics.app_version}</strong>
              </span>
              <span>
                <small>{t.resources.diagnostics.coreVersion}</small>
                <strong>{diagnostics.core_version}</strong>
              </span>
              <span>
                <small>{t.resources.diagnostics.freeSpace}</small>
                <strong>
                  {diagnostics.disk_free_bytes === null
                    ? t.resources.diagnostics.unknown
                    : formatBytes(diagnostics.disk_free_bytes)}
                </strong>
              </span>
              <span>
                <small>{t.resources.diagnostics.taskState}</small>
                <strong>
                  {diagnostics.active_task
                    ? t.resources.diagnostics.taskRunning
                    : t.resources.diagnostics.taskIdle}
                </strong>
              </span>
            </div>
            <div className="diagnostics-resources">
              {diagnostics.resources.map((resource) => {
                // Three states, not two. The backend already separates the
                // resources that actually block a task (`blocking_resources`
                // is built from `not optional and not usable`); painting every
                // unusable row red sent users off to install yt-dlp they had
                // no use for, and the tokeniser they do not need at all.
                const blocking = diagnostics.blocking_resources.includes(
                  resource.id,
                );
                const missing = !isUsable(resource);
                const state = !missing
                  ? "is-ready"
                  : blocking
                    ? "is-failed"
                    : "is-advisory";
                return (
                  <span
                    className={`resource-label ${state}`}
                    key={resource.id}
                    title={resource.detail}
                  >
                    {missing ? (
                      blocking ? (
                        <AlertCircle size={12} />
                      ) : (
                        <Info size={12} />
                      )
                    ) : (
                      <Check size={12} />
                    )}
                    {getResourceInfo(resource.id, t).title}
                  </span>
                );
              })}
            </div>
            <details className="diagnostics-paths">
              <summary>{t.resources.diagnostics.showPaths}</summary>
              <div>
                {Object.entries(diagnostics.paths).map(([key, path]) => (
                  <span key={key}>
                    <small>
                      {(t.resources.diagnostics.paths as Record<string, string>)[key] ?? key}
                    </small>
                    <code title={path}>{path}</code>
                  </span>
                ))}
                <span>
                  <small>{t.resources.diagnostics.python}</small>
                  <code title={diagnostics.python_executable}>
                    {diagnostics.python_executable}
                  </code>
                </span>
                {/* The managed models directory is what the UI can move and
                    purge, but it is not where the weights are when the
                    conventional cache already had them. Showing only the
                    managed path made those two actions look like they covered
                    several GB that were never in it. */}
                {modelsElsewhere ? (
                  <>
                    <span>
                      <small>{t.resources.diagnostics.modelsInUse}</small>
                      <code title={diagnostics.model_locations?.hf_home}>
                        {diagnostics.model_locations?.hf_home}
                      </code>
                    </span>
                    <span>
                      <small>{t.resources.diagnostics.separatorInUse}</small>
                      <code title={diagnostics.model_locations?.separator}>
                        {diagnostics.model_locations?.separator}
                      </code>
                    </span>
                  </>
                ) : null}
                <span className="diagnostics-interpreter">
                  <small>
                    {interpreter?.configured
                      ? t.resources.diagnostics.pythonConfigured
                      : t.resources.diagnostics.pythonAuto}
                  </small>
                  {interpreter?.found ? (
                    <code title={interpreter.found}>
                      {interpreter.found}
                      {interpreter.version ? ` · ${interpreter.version}` : ""}
                    </code>
                  ) : (
                    <strong className="is-failed">
                      {t.resources.diagnostics.pythonMissing}
                    </strong>
                  )}
                  <span className="diagnostics-interpreter-actions">
                    <button
                      type="button"
                      className="button button-secondary button-compact"
                      disabled={pythonBusy !== ""}
                      onClick={() => runPythonAction("choose")}
                    >
                      {t.resources.diagnostics.pythonChoose}
                    </button>
                    {interpreter?.configured ? (
                      <button
                        type="button"
                        className="button button-secondary button-compact"
                        disabled={pythonBusy !== ""}
                        onClick={() => runPythonAction("clear")}
                      >
                        {t.resources.diagnostics.pythonClear}
                      </button>
                    ) : null}
                  </span>
                </span>
              </div>
              {interpreter?.detail ? (
                <p className="diagnostics-interpreter-detail">{interpreter.detail}</p>
              ) : null}
              {pythonNotice ? (
                <p className="diagnostics-interpreter-detail">{pythonNotice}</p>
              ) : null}
            </details>
          </div>
        ) : null}
      </section>

      <section className="storage-card">
        <div className="storage-card-main">
          <span className="resource-large-icon">
            <HardDrive size={20} />
          </span>
          <div className="storage-card-copy">
            <div className="storage-card-title">
              <strong>{t.resources.storage.title}</strong>
              <span className="resource-label">
                {storage.relocated
                  ? t.resources.storage.custom
                  : t.resources.storage.default}
              </span>
            </div>
            <p>{t.resources.storage.description}</p>
            <code title={storage.big_data}>{storage.big_data || "—"}</code>
          </div>
        </div>
        <div className="storage-actions">
          <button
            type="button"
            className="button button-secondary button-compact"
            disabled={maintenanceBusy !== ""}
            onClick={() => void runStorageMaintenance("move")}
          >
            {maintenanceBusy === "move" ? (
              <LoaderCircle size={14} className="spin" />
            ) : (
              <FolderOpen size={14} />
            )}
            {t.resources.storage.move}
          </button>
          {storage.relocated ? (
            <button
              type="button"
              className="button button-secondary button-compact"
              disabled={maintenanceBusy !== ""}
              onClick={() => void runStorageMaintenance("reset")}
            >
              {maintenanceBusy === "reset" ? (
                <LoaderCircle size={14} className="spin" />
              ) : (
                <RotateCcw size={14} />
              )}
              {t.resources.storage.reset}
            </button>
          ) : null}
          <button
            type="button"
            className="button button-danger-quiet button-compact"
            disabled={maintenanceBusy !== ""}
            onClick={() => setPurgeConfirmOpen(true)}
          >
            <Trash2 size={14} />
            {t.resources.storage.purge}
          </button>
        </div>
        {maintenanceMessage ? (
          <p className="storage-message is-success">{maintenanceMessage}</p>
        ) : null}
        {maintenanceError ? (
          <p className="storage-message is-error">{maintenanceError}</p>
        ) : null}
      </section>

      <section className="resource-manager-list">
        {resources.map((resource) => {
          const resourceInfo = getResourceInfo(resource.id, t);
          const resourceSize = RESOURCE_SIZES[resource.id] || 0;
          const install = installs.find(
            (candidate) => candidate.resource_id === resource.id,
          );
          // "ready" here drives the finished look and the open-directory
          // action. An outdated copy is installed, so it gets neither the
          // download affordance nor the finished one -- it gets its own.
          const outdated = resource.state === "outdated" && install === undefined;
          const ready =
            (resource.state === "ready" || install?.state === "ready") &&
            !outdated;
          const running =
            install?.state === "queued" || install?.state === "running";
          const paused = install?.state === "paused";
          const failed = install?.state === "failed";
          const systemPythonAvailable =
            resource.id === "uv" && resource.reuses_system_python === true;
          // The model weights are fetched by the managed interpreter, so there
          // is nothing to run before it exists. A button that fails on click
          // would be worse than one that says what is missing.
          const blockedBy = ready
            ? ""
            : unresolvedDependency(resource, resources);
          return (
            <article
              className={`resource-card${running ? " is-installing" : ""
                }${failed ? " is-failed" : ""}`}
              key={resource.id}
            >
              <span className="resource-large-icon">
                {running ? (
                  <LoaderCircle size={20} className="spin" />
                ) : failed ? (
                  <AlertCircle size={20} />
                ) : (
                  <HardDrive size={20} />
                )}
              </span>
              <div className="resource-card-main">
                <div className="resource-card-heading">
                  <div className="resource-card-copy">
                    <div>
                      <h2>{resourceInfo.title}</h2>
                      <span
                        className={`resource-label${ready ? " is-ready" : ""
                          }${running ? " is-busy" : ""}${failed ? " is-failed" : ""
                          }`}
                      >
                        {ready ? (
                          <>
                            <Check size={12} /> {t.resources.status.installed}
                          </>
                        ) : outdated ? (
                          t.resources.status.updateAvailable
                        ) : running ? (
                          t.resources.status.processing
                        ) : paused ? (
                          t.resources.status.paused
                        ) : failed ? (
                          t.resources.status.failed
                        ) : systemPythonAvailable ? (
                          t.resources.status.systemPythonAvailable
                        ) : resource.id === "uv" ? (
                          t.resources.status.needsSetup
                        ) : (
                          t.resources.status.needDownload
                        )}
                      </span>
                    </div>
                    <p>{resourceInfo.detail}</p>
                    <div className="resource-meta">
                      <small>
                        {resource.version === "on-demand"
                          ? // The backend sends a token for rows it does not
                            // version (the model weights); the label is ours to
                            // translate, not its to hardcode in one language.
                            t.resources.meta.onDemand
                          : <>
                            {t.resources.meta.targetVersion}：{resource.version}
                            {outdated && resource.installed_version
                              ? `（${t.resources.meta.installedVersion}：${resource.installed_version}）`
                              : ""}
                          </>}
                      </small>
                      {!ready && resourceSize > 0 && (
                        <small className="resource-size">
                          {t.resources.meta.downloadSize}：{formatBytes(resourceSize)}
                        </small>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    className={`button ${ready ? "button-secondary" : "button-primary"
                      }`}
                    disabled={blockedBy !== ""}
                    title={
                      blockedBy
                        ? t.resources.blockedBy.replace(
                          "{resource}",
                          getResourceInfo(blockedBy, t).title || blockedBy,
                        )
                        : undefined
                    }
                    onClick={() => handleInstallClick(resource.id)}
                  >
                    {ready ? (
                      <FolderOpen size={14} />
                    ) : running ? (
                      <Pause size={14} />
                    ) : paused ? (
                      <Play size={14} />
                    ) : (
                      <Download size={14} />
                    )}
                    {ready
                      ? t.resources.actions.openDirectory
                      : outdated
                        ? t.resources.actions.update
                        : running
                          ? t.resources.actions.pauseDownload
                          : paused || failed
                            ? t.resources.actions.continueDownload
                            : systemPythonAvailable
                              ? t.resources.actions.installAIDeps
                              : resource.id === "uv"
                                ? t.resources.actions.checkAndInstall
                              : t.resources.actions.downloadAndInstall}
                  </button>
                </div>
                {install ? (
                  <div className="resource-install-detail">
                    {running && install.total > 0 ? (
                      <DownloadProgress
                        name={install.message}
                        downloaded={install.downloaded}
                        total={install.total}
                        bytesPerSecond={install.bytes_per_second}
                      />
                    ) : running ? (
                      <div className="resource-indeterminate">
                        <span className="indeterminate-track">
                          <i />
                        </span>
                        <strong>{install.message}</strong>
                      </div>
                    ) : (
                      <strong className="resource-install-message">
                        {install.message}
                      </strong>
                    )}
                    {install.error ? (
                      <p className="resource-error">{install.error}</p>
                    ) : null}
                    {install.logs.length ? (
                      <pre className="resource-install-log">
                        {install.logs.slice(-3).join("\n")}
                      </pre>
                    ) : null}
                    <div className="resource-paths">
                      <span title={install.cache_path}>
                        {t.resources.paths.cachePath}：{install.cache_path}
                      </span>
                      <span title={install.install_path}>
                        {t.resources.paths.installPath}：{install.install_path}
                      </span>
                    </div>
                    <div className="resource-location-actions">
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => onOpenLocation(resource.id, "cache")}
                      >
                        <FolderOpen size={13} /> {t.resources.paths.openCacheDir}
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => onOpenLocation(resource.id, "install")}
                      >
                        <FolderOpen size={13} /> {t.resources.paths.openInstallDir}
                      </button>
                    </div>
                  </div>
                ) : resource.detail ? (
                  <p className={failed ? "resource-error" : "resource-detail"}>
                    {resource.detail}
                  </p>
                ) : null}
              </div>
            </article>
          );
        })}
      </section>

      <div className="resource-info-note">
        <strong>{t.resources.sourceNote.title}</strong>
        <p>{t.resources.sourceNote.description}</p>
      </div>

      <div className="resource-info-note">
        <strong>{t.resources.modelNote.title}</strong>
        <p>
          {t.resources.modelNote.description}
        </p>
      </div>

      {/* 下载确认对话框 */}
      {confirmOpen && pendingResourceInfo && (
        <div className="dialog-overlay" onClick={closeInstallConfirm}>
          <div
            aria-busy={pythonConfirm && pythonPreflightBusy}
            aria-labelledby="resource-confirm-title"
            aria-modal="true"
            className={`dialog-card resource-confirm-dialog${pythonConfirm ? " is-python" : ""}`}
            role="dialog"
            onClick={(e) => e.stopPropagation()}
          >
            {pythonConfirm ? (
              <>
                <div className="resource-confirm-icon">
                  {pythonPreflightBusy ? (
                    <LoaderCircle size={24} className="spin" />
                  ) : pythonFound ? (
                    <Check size={24} />
                  ) : (
                    <AlertTriangle size={24} />
                  )}
                </div>
                <h3 id="resource-confirm-title">
                  {pythonPreflightBusy
                    ? t.resources.confirm.python.checkingTitle
                    : pythonFound
                      ? t.resources.confirm.python.foundTitle
                      : pythonPreflightError
                        ? t.resources.confirm.python.checkFailedTitle
                        : t.resources.confirm.python.missingTitle}
                </h3>
                <div
                  aria-live="polite"
                  className="python-preflight-status"
                  role="status"
                >
                  {pythonPreflightBusy ? (
                    <p>{t.resources.confirm.python.checking}</p>
                  ) : pythonFound ? (
                    <>
                      <p>
                        {t.resources.confirm.python.found.replace(
                          "{version}",
                          pythonPreflight?.version || "3.12",
                        )}
                      </p>
                      <code className="python-preflight-path" title={pythonFound}>
                        {pythonFound}
                      </code>
                    </>
                  ) : (
                    <p className="python-preflight-detail">
                      {pythonPreflightError ||
                        pythonPreflight?.detail ||
                        t.resources.confirm.python.missing}
                    </p>
                  )}
                </div>
                <div className="dialog-actions python-preflight-actions">
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={closeInstallConfirm}
                  >
                    {t.resources.confirm.cancel}
                  </button>
                  {!pythonPreflightBusy ? (
                    <button
                      type="button"
                      className="button button-secondary"
                      disabled={pythonBusy !== ""}
                      onClick={() => void choosePythonForInstall()}
                    >
                      {pythonBusy === "choose" ? (
                        <LoaderCircle size={14} className="spin" />
                      ) : (
                        <FolderOpen size={14} />
                      )}
                      {t.resources.confirm.python.choose}
                    </button>
                  ) : null}
                  {pythonPreflightBusy ? null : pythonPreflightError ? (
                    <button
                      type="button"
                      className="button button-primary"
                      disabled={pythonBusy !== ""}
                      onClick={startPythonPreflight}
                    >
                      <RotateCcw size={14} />
                      {t.resources.confirm.python.retry}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="button button-primary"
                      disabled={pythonBusy !== ""}
                      onClick={handleConfirmInstall}
                    >
                      <Download size={14} />
                      {pythonFound
                        ? t.resources.confirm.python.useLocal
                        : t.resources.confirm.python.download}
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <div className="resource-confirm-icon">
                  <AlertTriangle size={24} />
                </div>
                <h3 id="resource-confirm-title">{t.resources.confirm.title}</h3>
                <p>
                  {t.resources.confirm.message
                    .replace("{name}", pendingResourceInfo.title)
                    .replace("{size}", formatBytes(pendingResourceSize))}
                </p>
                <p className="confirm-warning-text">
                  {t.resources.confirm.warning}
                </p>
                <div className="dialog-actions">
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={closeInstallConfirm}
                  >
                    {t.resources.confirm.cancel}
                  </button>
                  <button
                    type="button"
                    className="button button-primary"
                    onClick={handleConfirmInstall}
                  >
                    <Download size={14} />
                    {t.resources.confirm.startDownload}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {purgeConfirmOpen ? (
        <div className="dialog-overlay" onClick={() => setPurgeConfirmOpen(false)}>
          <div className="dialog-card resource-confirm-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="resource-confirm-icon is-danger">
              <Trash2 size={24} />
            </div>
            <h3>{t.resources.storage.purgeTitle}</h3>
            <p>{t.resources.storage.purgeDescription}</p>
            <p className="confirm-warning-text">
              {t.resources.storage.purgePreserves}
            </p>
            <div className="dialog-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setPurgeConfirmOpen(false)}
              >
                {t.resources.confirm.cancel}
              </button>
              <button
                type="button"
                className="button button-danger-quiet"
                disabled={maintenanceBusy !== ""}
                onClick={() => void runStorageMaintenance("purge")}
              >
                {maintenanceBusy === "purge" ? (
                  <LoaderCircle size={14} className="spin" />
                ) : (
                  <Trash2 size={14} />
                )}
                {t.resources.storage.purgeConfirm}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
