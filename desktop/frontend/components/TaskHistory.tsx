"use client";

import {
  Ban,
  Clock3,
  Eraser,
  FileText,
  FolderOpen,
  Languages,
  Play,
  RotateCcw,
  Trash2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { fileName, summarizeTaskError } from "@/lib/formatters";
import { preferredTaskOutput } from "@/lib/subtitleOutputs";
import type { JobSnapshot } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";


interface TaskHistoryProps {
  tasks: JobSnapshot[];
  error?: string;
  /** A task is running or being checked: reuse rebuilds the form state, and
      unlike retry/resume there is no backend rejection to fall back on. */
  reuseDisabled?: boolean;
  onCancel: (taskId: string) => void;
  onRetry: (taskId: string) => void;
  onResume: (taskId: string) => void;
  onReuse: (snapshot: JobSnapshot) => void;
  onOpenOutput: (path: string) => void;
  onOpenTasksDirectory: () => void;
  onDeleteIntermediates: (taskId: string) => void;
  onDeleteRecord: (taskId: string) => void;
}


function taskId(snapshot: JobSnapshot): string {
  return snapshot.task_id ?? snapshot.taskId ?? "";
}


function taskTime(snapshot: JobSnapshot): string {
  const seconds = snapshot.updated_at ?? snapshot.created_at;
  if (!seconds) {
    return "";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(seconds * 1000));
}


export function TaskHistory({
  tasks,
  error,
  reuseDisabled,
  onCancel,
  onRetry,
  onResume,
  onReuse,
  onOpenOutput,
  onOpenTasksDirectory,
  onDeleteIntermediates,
  onDeleteRecord,
}: TaskHistoryProps) {
  const { t } = useLanguage();
  const [revealedId, setRevealedId] = useState("");
  const hold = useRef<number | null>(null);
  const holdStart = useRef({ x: 0, y: 0 });
  const stopHold = () => {
    if (hold.current !== null) window.clearTimeout(hold.current);
    hold.current = null;
  };
  useEffect(() => () => {
    if (hold.current !== null) window.clearTimeout(hold.current);
  }, []);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          {/* <p className="page-kicker">{t.history.kicker}</p> */}
          <h1>{t.history.title}</h1>
          <p>{t.history.description}</p>
          <small className="field-help">{t.history.deleteRecordHint}</small>
        </div>
        <button
          type="button"
          className="button button-secondary"
          onClick={() => onOpenTasksDirectory()}
        >
          <FolderOpen size={14} />
          {t.history.openTasksDir}
        </button>
      </header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      {tasks.length ? (
        <section className="history-list">
          {tasks.map((snapshot) => {
            const id = taskId(snapshot);
            const output = preferredTaskOutput(snapshot.outputs);
            const stateLabel = t.history.status[snapshot.state];
            return (
              <article
                className={`history-row${revealedId === id ? " is-delete-revealed" : ""}`}
                key={id}
                tabIndex={0}
                onPointerDown={(event) => {
                  if (snapshot.state === "running" || event.button !== 0 || (event.target instanceof Element && event.target.closest("button"))) return;
                  stopHold();
                  holdStart.current = { x: event.clientX, y: event.clientY };
                  hold.current = window.setTimeout(() => { setRevealedId(id); hold.current = null; }, 550);
                }}
                onPointerMove={(event) => {
                  if (Math.hypot(event.clientX - holdStart.current.x, event.clientY - holdStart.current.y) > 10) stopHold();
                }}
                onPointerUp={stopHold}
                onPointerCancel={stopHold}
                onPointerLeave={stopHold}
                onContextMenu={(event) => {
                  if (snapshot.state === "running") return;
                  event.preventDefault();
                  stopHold();
                  setRevealedId(id);
                }}
                onKeyDown={(event) => {
                  if (snapshot.state !== "running" && (event.key === "Delete" || event.key === "ContextMenu" || (event.shiftKey && event.key === "F10"))) {
                    event.preventDefault();
                    setRevealedId(id);
                  }
                }}
              >
                <span className="history-icon">
                  <FileText size={17} />
                </span>
                <div className="history-copy">
                  <strong>{fileName(snapshot.request?.input ?? t.history.unknownFile)}</strong>
                  <span>
                    {stateLabel}
                    {taskTime(snapshot) ? ` · ${taskTime(snapshot)}` : ""}
                  </span>
                  {snapshot.error ? (
                    <small title={snapshot.error}>
                      {summarizeTaskError(snapshot.error)}
                    </small>
                  ) : null}
                </div>
                <div className="history-side">
                  <span className={`history-state is-${snapshot.state}`}>
                    {stateLabel}
                  </span>
                  <div className="history-actions">
                    {snapshot.state === "running" ? (
                      <button
                        type="button"
                        className="button button-danger-quiet button-compact"
                        onClick={() => onCancel(id)}
                      >
                        <Ban size={14} /> {t.history.cancelTask}
                      </button>
                    ) : snapshot.state === "interrupted" ? (
                      <button
                        type="button"
                        className="button button-primary button-compact"
                        onClick={() => onResume(id)}
                      >
                        <Play size={14} /> {t.history.resume}
                      </button>
                    ) : snapshot.state === "failed" ||
                      snapshot.state === "cancelled" ? (
                      <button
                        type="button"
                        className="button button-secondary button-compact"
                        onClick={() => onRetry(id)}
                      >
                        <RotateCcw size={14} /> {t.history.retry}
                      </button>
                    ) : snapshot.state === "completed" ? (
                      <>
                        {/* Only recognition-only runs: a completed final-srt
                            directory would satisfy the LLM stage's existence
                            check too, and "continue" would republish it. */}
                        {snapshot.request?.stage === "raw-srt" &&
                        snapshot.request?.output ? (
                          <button
                            type="button"
                            className="button button-primary button-compact"
                            disabled={reuseDisabled}
                            onClick={() => onReuse(snapshot)}
                          >
                            <Languages size={14} /> {t.history.continueLlm}
                          </button>
                        ) : null}
                        {output ? (
                          <button
                            type="button"
                            className="button button-secondary button-compact"
                            onClick={() => onOpenOutput(output)}
                          >
                            <FolderOpen size={14} /> {t.history.openResult}
                          </button>
                        ) : null}
                      </>
                    ) : null}
                    {/* Every state but running, failed ones included: a run
                        that died is exactly the one that left a separated
                        vocal track behind, and it never got to tidy up. */}
                    {snapshot.state !== "running" && snapshot.request?.output ? (
                      <button
                        type="button"
                        className="button button-secondary button-compact"
                        onClick={() => onDeleteIntermediates(id)}
                      >
                        <Eraser size={14} /> {t.history.deleteIntermediates}
                      </button>
                    ) : null}
                    {snapshot.state !== "running" ? (
                      <button
                        type="button"
                        className="button button-danger-quiet button-compact history-record-delete"
                        aria-label={`${t.history.deleteRecord}: ${fileName(snapshot.request?.input ?? t.history.unknownFile)}`}
                        onClick={() => onDeleteRecord(id)}
                      >
                        <Trash2 size={14} /> {t.history.deleteRecord}
                      </button>
                    ) : null}
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <section className="empty-state">
          <Clock3 size={24} />
          <h2>{t.history.emptyTitle}</h2>
          <p>{t.history.emptyDescription}</p>
        </section>
      )}
    </div>
  );
}
