"use client";

import {
  Check,
  ChevronDown,
  Circle,
  Download,
  FolderOpen,
  CircleStop,
  LoaderCircle,
  RotateCcw,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { desktopApi } from "@/lib/bridge";
import { formatDuration, summarizeTaskError } from "@/lib/formatters";
import type { TaskState } from "@/lib/state";
import type { PipelineStage } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";
import { useToast } from "./ToastProvider";


const pipelineStages: PipelineStage[] = [
  "vocal",
  "aligned",
  "stable",
  "raw-srt",
  "translated-srt",
  "final-srt",
];


interface ProcessingViewProps {
  task: TaskState;
  /** Nothing has finished on this machine yet: weights and warm-up come first. */
  firstRun?: boolean;
  /** The weights are already cached, so the notice must not promise a download. */
  modelsReady?: boolean;
  onCancel: () => void;
  onRetry: () => void;
}


export function ProcessingView({
  task,
  firstRun,
  modelsReady,
  onCancel,
  onRetry,
}: ProcessingViewProps) {
  const { t } = useLanguage();
  const { showSuccess } = useToast();
  const [logsOpen, setLogsOpen] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportedLogPath, setExportedLogPath] = useState("");
  const [exportError, setExportError] = useState("");
  const [now, setNow] = useState(Date.now());
  const logDrawerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setExportedLogPath("");
    setExportError("");
  }, [task.taskId]);
  useEffect(() => {
    if (task.phase !== "running") {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [task.phase]);
  useEffect(() => {
    if (!logsOpen || !logDrawerRef.current) {
      return;
    }
    logDrawerRef.current.scrollTop = logDrawerRef.current.scrollHeight;
  }, [logsOpen, task.logs]);
  const elapsed = task.startedAt
    ? Math.max(0, (now - task.startedAt) / 1000)
    : 0;
  const targetIndex = pipelineStages.indexOf(task.request.stage);
  const activeIndex = task.currentStage
    ? pipelineStages.indexOf(task.currentStage)
    : 0;
  const visibleStages = pipelineStages.slice(0, Math.max(0, targetIndex) + 1);
  const stageLabels: Record<PipelineStage, string> = {
    vocal: t.processing.stages.vocal,
    aligned: t.processing.stages.aligned,
    stable: t.processing.stages.stable,
    "raw-srt": t.processing.stages.rawSrt,
    "translated-srt": t.processing.stages.translatedSrt,
    "final-srt": t.processing.stages.finalSrt,
  };
  const headline = task.phase === "failed"
    ? t.processing.failedHeadline
    : task.currentStage
      ? stageLabels[task.currentStage]
      : t.processing.starting;
  const exportLog = async () => {
    if (!task.taskId) return;
    setExportBusy(true);
    setExportError("");
    try {
      const result = await desktopApi.exportTaskLog(task.taskId);
      if (!result.cancelled && result.path) {
        setExportedLogPath(result.path);
        showSuccess(t.processing.logExported, `task-log-exported-${task.taskId}`);
      }
    } catch (error) {
      setExportError(error instanceof Error ? error.message : t.processing.logExportFailed);
    } finally {
      setExportBusy(false);
    }
  };
  const openExportLocation = async () => {
    try {
      await desktopApi.openTaskLogExportLocation();
      setExportError("");
    } catch (error) {
      setExportError(error instanceof Error ? error.message : t.processing.logLocationFailed);
    }
  };

  return (
    <div className="page processing-page">
      <header className="page-header">
        <div>
          {/* <p className="page-kicker">ACTIVE TASK</p> */}
          <h1>
            {task.phase === "failed"
              ? t.processing.failedTitle
              : t.processing.runningTitle}
          </h1>
          <p>{task.selectedFile}</p>
        </div>
        <div className="elapsed">
          <span>{t.processing.elapsed}</span>
          <strong>{formatDuration(elapsed)}</strong>
        </div>
      </header>

      <section className={`processing-card ${task.phase === "failed" ? "is-failed" : ""}`}>
        <div className="processing-hero">
          <div className="processing-mark">
            {task.phase === "failed" ? (
              <CircleStop size={24} />
            ) : (
              <LoaderCircle size={25} className="spin" />
            )}
          </div>
          <div>
            <p>
              {task.phase === "failed"
                ? t.processing.needsAttention
                : t.processing.currentStage}
            </p>
            <h2>{headline}</h2>
            <span title={task.phase === "failed" ? task.error?.message : undefined}>
              {task.phase === "failed"
                ? summarizeTaskError(task.error?.message)
                : task.statusMessage || t.processing.initializing}
            </span>
          </div>
        </div>

        {firstRun && task.phase !== "failed" ? (
          <div className="inline-note" role="note">
            {modelsReady
              ? t.newTask.firstRunNoticeWarm
              : t.newTask.firstRunNotice}
          </div>
        ) : null}

        <ol className="stage-list">
          {visibleStages.map((stage, index) => {
            const done = index < activeIndex;
            const active = index === activeIndex && task.phase !== "failed";
            // A stage the run skipped because its output was already there.
            // The tick alone would claim it just did the work.
            const reused = task.reusedStages.includes(stage) && (done || active);
            const skipped = task.skippedStages?.includes(stage) ?? false;
            return (
              <li
                key={stage}
                className={`${done ? "is-done" : ""}${active ? " is-active" : ""}${reused ? " is-reused" : ""}${skipped ? " is-skipped" : ""}`}
              >
                <span className="stage-symbol">
                  {skipped ? (
                    <X size={13} />
                  ) : done || reused ? (
                    <Check size={13} />
                  ) : active ? (
                    <LoaderCircle size={13} className="spin" />
                  ) : (
                    <Circle size={10} />
                  )}
                </span>
                <span>{stageLabels[stage]}</span>
                {reused ? (
                  <small className="stage-note">{t.processing.stageReused}</small>
                ) : null}
                {skipped ? <small className="stage-note">{t.processing.stageSkipped}</small> : null}
              </li>
            );
          })}
        </ol>

        <div className="processing-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={() => setLogsOpen((value) => !value)}
          >
            {t.processing.logs}
            <ChevronDown
              size={14}
              className={logsOpen ? "is-rotated" : ""}
            />
          </button>
          {task.phase === "failed" ? (
            <button
              type="button"
              className="button button-primary"
              onClick={onRetry}
            >
              <RotateCcw size={14} />
              {t.processing.retry}
            </button>
          ) : (
            <button
              type="button"
              className="button button-danger-quiet"
              onClick={onCancel}
            >
              <CircleStop size={14} />
              {t.processing.cancel}
            </button>
          )}
        </div>

        {logsOpen ? (
          <>
            <div className="log-toolbar">
              {exportedLogPath ? (
                <button type="button" className="button button-secondary button-compact" onClick={() => void openExportLocation()}>
                  <FolderOpen size={13} />{t.processing.openLogLocation}
                </button>
              ) : null}
              <button
                type="button"
                className="button button-secondary button-compact"
                disabled={!task.taskId || exportBusy}
                onClick={() => void exportLog()}
              >
                <Download size={13} />
                {t.processing.exportLogs}
              </button>
            </div>
            {exportError ? <p className="routing-error" role="alert">{exportError}</p> : null}
          <div
            ref={logDrawerRef}
            className="log-drawer"
            role="log"
            aria-label={t.processing.logAria}
            aria-live="polite"
          >
            {task.logs.length ? (
              task.logs.map((line, index) => (
                <div key={`${index}-${line}`}>{line}</div>
              ))
            ) : (
              <span>{t.processing.waitingLogs}</span>
            )}
          </div>
          </>
        ) : null}
      </section>
    </div>
  );
}
