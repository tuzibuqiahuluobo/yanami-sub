"use client";

import { AlertCircle, ArrowLeft, CheckCircle2, X } from "lucide-react";
import { useLanguage } from "./LanguageProvider";

export function PrerequisiteNotice({ message, origin, ready, onBack, onDismiss }: {
  message: string;
  origin: "new-task" | "batch" | "history";
  ready: boolean;
  onBack: () => void;
  onDismiss: () => void;
}) {
  const { language } = useLanguage();
  const english = language === "en";
  const destination = origin === "batch" ? (english ? "batch" : "批处理") :
    origin === "history" ? (english ? "history" : "历史记录") : (english ? "new task" : "新建任务");
  return <aside className={`prerequisite-notice${ready ? " is-ready" : ""}`} role="status">
    {ready ? <CheckCircle2 size={19} aria-hidden="true" /> : <AlertCircle size={19} aria-hidden="true" />}
    <div className="prerequisite-copy">
      <strong>{ready ? (english ? "Required resources are ready" : "所需资源已就绪") : (english ? "Action needed before continuing" : "继续前需要处理")}</strong>
      <span>{ready ? (english ? "Return to your task when you are ready." : "准备好后请返回任务继续。") : message}</span>
    </div>
    <button type="button" className="button button-secondary button-compact" onClick={onBack}><ArrowLeft size={14} />{english ? `Back to ${destination}` : `返回${destination}继续`}</button>
    <button type="button" className="icon-button" onClick={onDismiss} aria-label={english ? "Dismiss guidance" : "关闭任务引导"}><X size={15} /></button>
  </aside>;
}
