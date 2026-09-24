"use client";

import { Check, X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { formatBytes, formatPercent } from "@/lib/formatters";
import type { TaskState } from "@/lib/state";
import type { PipelineStage, Route, UpdateInstallSnapshot } from "@/lib/types";

import { useLanguage } from "./LanguageProvider";


interface ToastItem {
  id: string;
  instance: number;
  message: string;
}

interface ToastContextValue {
  toasts: ToastItem[];
  showSuccess: (message: string, id?: string) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);


export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showSuccess = useCallback((message: string, stableId?: string) => {
    const instance = nextId.current += 1;
    const id = stableId ?? `success-${instance}`;
    setToasts((current) => {
      const withoutDuplicate = current.filter((toast) => toast.id !== id);
      return [...withoutDuplicate, { id, instance, message }].slice(-3);
    });
  }, []);

  return (
    <ToastContext.Provider value={{ toasts, showSuccess, dismiss }}>
      {children}
    </ToastContext.Provider>
  );
}


export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used inside ToastProvider");
  }
  return { showSuccess: context.showSuccess };
}


function SuccessToast({
  toast,
  onDismiss,
}: {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}) {
  const { t } = useLanguage();

  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(toast.id), 4500);
    return () => window.clearTimeout(timer);
  }, [onDismiss, toast.id, toast.message]);

  return (
    <div className="toast-item toast-success" role="status">
      <span className="toast-status-icon" aria-hidden="true">
        <Check size={14} strokeWidth={2.4} />
      </span>
      <span className="toast-message">{toast.message}</span>
      <button type="button" className="toast-dismiss" aria-label={t.toast.close} onClick={() => onDismiss(toast.id)}>
        <X size={14} />
      </button>
    </div>
  );
}


function TaskProgressItem({ task }: { task: TaskState }) {
  const { t } = useLanguage();
  const stageLabels: Record<PipelineStage, string> = {
    vocal: t.processing.stages.vocal,
    aligned: t.processing.stages.aligned,
    stable: t.processing.stages.stable,
    "raw-srt": t.processing.stages.rawSrt,
    "translated-srt": t.processing.stages.translatedSrt,
    "final-srt": t.processing.stages.finalSrt,
  };

  return (
    <div className="toast-item update-progress-toast" role="status" aria-live="polite">
      <span className="update-progress-ring is-indeterminate" role="progressbar" aria-label={t.processing.runningTitle}>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle className="update-ring-track" cx="12" cy="12" r="9" />
          <circle className="update-ring-value" cx="12" cy="12" r="9" pathLength="100" />
        </svg>
      </span>
      <span className="update-progress-copy">
        <strong>{t.processing.runningTitle}</strong>
        <small>{(task.currentStage && stageLabels[task.currentStage]) || t.processing.starting}</small>
      </span>
    </div>
  );
}


function UpdateProgressItem({ install }: { install: UpdateInstallSnapshot }) {
  const { t } = useLanguage();
  const ready = install.state === "ready";
  const determinate = install.total > 0;
  const percent = determinate
    ? Math.min(100, Math.max(0, (install.downloaded / install.total) * 100))
    : 0;

  if (ready) {
    return (
      <div className="toast-item update-progress-toast is-ready" role="status" aria-live="polite">
        <span className="toast-status-icon" aria-hidden="true">
          <Check size={14} strokeWidth={2.4} />
        </span>
        <span className="toast-message">{t.toast.updateDownloaded}</span>
      </div>
    );
  }

  const downloading = install.phase === "downloading";
  return (
    <div className="toast-item update-progress-toast">
      <span
        className={`update-progress-ring${determinate ? "" : " is-indeterminate"}`}
        role="progressbar"
        aria-label={downloading ? t.toast.updateDownloading : t.toast.updateInstalling}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={determinate ? Math.round(percent) : undefined}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle className="update-ring-track" cx="12" cy="12" r="9" />
          <circle
            className="update-ring-value"
            cx="12"
            cy="12"
            r="9"
            pathLength="100"
            style={{ strokeDashoffset: determinate ? 100 - percent : 72 }}
          />
        </svg>
      </span>
      <span className="update-progress-copy">
        <strong>{downloading ? t.toast.updateDownloading : t.toast.updateInstalling}</strong>
        <small>
          {downloading && determinate
            ? `${formatPercent(install.downloaded, install.total)} · ${formatBytes(install.downloaded)} / ${formatBytes(install.total)}`
            : install.version}
        </small>
      </span>
    </div>
  );
}


export function ToastViewport({
  updateInstall,
  task,
  route,
}: {
  updateInstall: UpdateInstallSnapshot | null;
  task: TaskState;
  route: Route;
}) {
  const context = useContext(ToastContext);
  const { t } = useLanguage();
  const [showCompletedUpdate, setShowCompletedUpdate] = useState(false);
  const activeUpdate =
    updateInstall?.state === "queued" || updateInstall?.state === "running";

  useEffect(() => {
    if (activeUpdate) {
      setShowCompletedUpdate(true);
      return;
    }
    if (updateInstall?.state !== "ready") {
      setShowCompletedUpdate(false);
      return;
    }
    setShowCompletedUpdate(true);
    const timer = window.setTimeout(() => setShowCompletedUpdate(false), 4500);
    return () => window.clearTimeout(timer);
  }, [activeUpdate, updateInstall?.state, updateInstall?.updated_at]);

  if (!context) {
    return null;
  }

  const showUpdate =
    updateInstall !== null &&
    (activeUpdate || (updateInstall.state === "ready" && showCompletedUpdate));
  const showTask = route !== "new-task" && task.phase === "running";

  if (!context.toasts.length && !showUpdate && !showTask) {
    return null;
  }

  return (
    <aside className="toast-viewport" aria-label={t.toast.notifications}>
      <div className="toast-list" aria-live="polite" aria-atomic="false">
        {context.toasts.map((toast) => (
          <SuccessToast
            key={`${toast.id}-${toast.instance}`}
            toast={toast}
            onDismiss={context.dismiss}
          />
        ))}
      </div>
      {showTask ? <TaskProgressItem task={task} /> : null}
      {showUpdate ? <UpdateProgressItem install={updateInstall} /> : null}
    </aside>
  );
}
