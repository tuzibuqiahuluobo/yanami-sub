"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import { useLanguage } from "./LanguageProvider";

export function AgentConfigDialog({ name, children, onDismiss, status, detail }: { name: string; children: ReactNode; onDismiss?: () => void; status?: ReactNode; detail?: string }) {
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const { language } = useLanguage();
  const en = language === "en";
  const dismiss = () => { setOpen(false); onDismiss?.(); };
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  return <div className="agent-config-row">
    <div className="agent-config-summary"><strong>{name}</strong>{detail ? <small>{detail}</small> : null}</div>
    {status}
    <button type="button" className="button button-secondary button-compact" aria-label={`${name} ${en ? "settings" : "设置"}`} onClick={() => setOpen(true)}>{en ? "Configure" : "配置"}</button>
    <dialog ref={dialog} className="dialog-card agent-config-dialog" aria-label={name + (en ? " settings" : " 设置")} onCancel={dismiss}>
      <div className="settings-section-heading"><h3>{name}</h3>
        <button type="button" className="icon-button" onClick={dismiss} aria-label={en ? "Close" : "关闭"}><X size={18} /></button></div>
      {children}
      <p className="field-help">{en ? "Path changes are saved only with Save path. Shared routing options remain in the main settings." : "路径更改需点击“保存路径”才生效。通用路由设置仍在主设置区。"}</p>
    </dialog>
  </div>;
}
