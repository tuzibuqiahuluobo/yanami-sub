"use client";

import {
  Check,
  ExternalLink,
  FileText,
  FolderOpen,
  RotateCcw,
  X,
} from "lucide-react";

import { fileName } from "@/lib/formatters";
import type { TaskState } from "@/lib/state";
import {
  preferredTaskOutput,
  taskOutputEntries,
} from "@/lib/subtitleOutputs";
import { useLanguage } from "./LanguageProvider";
import { useEffect, useState } from "react";
import { desktopApi } from "@/lib/bridge";


interface CompletedViewProps {
  task: TaskState;
  onOpen: (path: string) => void;
  onReset: () => void;
}


export function CompletedView({
  task,
  onOpen,
  onReset,
}: CompletedViewProps) {
  const { t, language } = useLanguage();
  const [logPath, setLogPath] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void desktopApi.listTaskLogs(task.taskId ?? "").then((result) => {
      if (active) setLogPath(result.items.find((row) => row.id === task.taskId)?.log_path ?? "");
    }).catch((caught) => { if (active) setError(String(caught)); });
    return () => { active = false; };
  }, [task.taskId]);
  const outputLabels: Record<string, string> = t.completed.labels;
  const outputs = taskOutputEntries(task.outputs);
  const preferred = preferredTaskOutput(task.outputs);
  const rawFallback = ["translated-srt", "final-srt"].includes(task.request.stage)
    && Boolean(task.outputs.rawSrt)
    && !task.outputs.translatedSrt
    && !task.outputs.finalSrt;

  return (
    <div className="page completed-page">
      <header className="page-header">
        <div>
          {/* <p className="page-kicker">COMPLETED</p> */}
          <h1>{t.completed.readyTitle}</h1>
          <p>{task.selectedFile}</p>
        </div>
        <span className={`completion-badge${rawFallback ? " is-partial" : ""}`}>
          {rawFallback ? <X size={14} /> : <Check size={14} />}
          {rawFallback ? t.completed.rawFallbackBadge : t.completed.done}
        </span>
      </header>

      <section className="completed-card">
        <div className="completed-summary">
          <div className={`success-mark${rawFallback ? " is-partial" : ""}`}>
            {rawFallback ? <X size={24} strokeWidth={2} /> : <Check size={24} strokeWidth={2} />}
          </div>
          <div>
            <p>{t.completed.summary}</p>
            <h2>{preferred ? fileName(preferred) : t.completed.fallbackName}</h2>
            <span>{rawFallback ? t.completed.rawFallback : t.completed.description}</span>
          </div>
        </div>

        <div className="output-list">
          {task.request.speaker_tracks && task.request.speaker_tracks !== "off" && !outputs.some(([key]) => key.startsWith("speaker:")) ? <p className="inline-note" role="status">{language === "en" ? "No speaker export was produced. Review the task log; the normal subtitle result is still available." : "分轨字幕未产出，请检查任务日志；普通字幕结果仍可使用。"}</p> : null}
          {task.request.diarize?.startsWith("judge-") && ["translated-srt", "final-srt"].includes(task.request.stage) && !task.outputs.speakerJudge ? <p className="inline-note" role="status">{language === "en" ? "No speaker-judge report was produced. Review the optional-stage log." : "本次未生成说话人裁判报告，请查看可选阶段日志。"}</p> : null}
          {outputs.map(([key, path]) => (
            <button
              type="button"
              className="output-row"
              key={key}
              onClick={() => onOpen(path)}
            >
              <span className="output-icon">
                <FileText size={16} />
              </span>
              <span>
                <strong>{key.startsWith("speaker:") ? `${language === "en" ? "Speaker export" : "分轨字幕"} · ${fileName(path)}` : key === "speakerTimeline" ? (language === "en" ? "Speaker timeline" : "说话人时间线") : key === "speakerJudge" ? (language === "en" ? "Speaker judge report" : "说话人裁判记录") : outputLabels[key] ?? key}</strong>
                <small className="result-path">{path}</small>
              </span>
              <ExternalLink size={14} />
            </button>
          ))}
        </div>

        <div className="result-location"><strong>{language === "en" ? "Task log" : "任务日志"}</strong><code className="result-path">{logPath || (language === "en" ? "Log not available yet" : "日志暂不可用")}</code><button type="button" className="button button-secondary button-compact" disabled={!task.taskId} onClick={async () => { try { await desktopApi.openTaskLogLocation(task.taskId!); } catch (caught) { setError(String(caught)); } }}>{language === "en" ? "Open log location" : "打开日志位置"}</button></div>
        {error ? <p role="alert" className="api-key-error">{error}</p> : null}
        <div className="completed-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={onReset}
          >
            <RotateCcw size={14} />
            {t.completed.newTask}
          </button>
          {preferred ? (
            <button
              type="button"
              className="button button-primary"
              onClick={() => onOpen(preferred)}
            >
              <FolderOpen size={15} />
              {t.completed.openDirectory}
            </button>
          ) : null}
        </div>
      </section>
    </div>
  );
}
