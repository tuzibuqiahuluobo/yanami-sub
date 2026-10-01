"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, RefreshCw, X } from "lucide-react";
import { desktopApi } from "@/lib/bridge";
import type { LocalAgentStatus } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";

interface Props {
  open: boolean;
  onClose: () => void;
  onProbe: () => Promise<LocalAgentStatus[]>;
}

export function WorkBuddyRepairDialog({ open, onClose, onProbe }: Props) {
  const { language } = useLanguage();
  const en = language === "en";
  const dialog = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    setMessage(""); setError("");
    const previous = document.activeElement as HTMLElement | null;
    const scroller = document.querySelector<HTMLElement>(".workspace");
    const overflow = scroller?.style.overflowY ?? "";
    if (scroller) scroller.style.overflowY = "hidden";
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const buttons = Array.from(dialog.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
      const first = buttons[0], last = buttons.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first?.focus();
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      if (scroller) scroller.style.overflowY = overflow;
      previous?.focus();
    };
  }, [open]);
  if (!open) return null;
  const perform = async (probe: boolean) => {
    setBusy(true); setError(""); setMessage("");
    try {
      if (probe) {
        const agent = (await onProbe()).find((item) => item.provider_tier === "LOCAL_WORKBUDDY");
        setMessage(agent?.available
          ? en ? "CLI available. Login, model access and quota are not verified; retry your task after signing in." : "CLI 可用。登录、模型权限和额度尚未验证；在官方客户端登录后请重试任务。"
          : en ? "CLI unavailable. Check the installation path and update WorkBuddy, then retry detection." : "CLI 不可用。请检查安装路径、更新 WorkBuddy 后重新检测。");
      } else {
        await desktopApi.openWorkBuddyLogin();
        setMessage(en ? "Official client opened. Complete sign-in there, then return and retry your task." : "已打开官方客户端。请在那里完成登录，再返回并重试任务。");
      }
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally { setBusy(false); }
  };
  return <div className="dialog-overlay" onClick={onClose}>
    <div ref={dialog} className="dialog-card workbuddy-repair-dialog" role="dialog" aria-modal="true" aria-labelledby="workbuddy-repair-title" aria-describedby="workbuddy-repair-description" onClick={(event) => event.stopPropagation()}>
      <div className="settings-section-heading">
        <h3 id="workbuddy-repair-title">{en ? "WorkBuddy sign-in repair" : "WorkBuddy 登录修复"}</h3>
        <button type="button" className="icon-button" aria-label={en ? "Close" : "关闭"} onClick={onClose}><X size={18} /></button>
      </div>
      <p id="workbuddy-repair-description">{en ? "Authentication required is a sign-in problem, not a network retry. Yanami Sub does not read or store vendor credentials." : "Authentication required 表示当前调用未通过认证，不是网络重试问题。Yanami Sub 不读取或保存厂商登录凭据。"}</p>
      <ol>
        <li>{en ? "Open the official WorkBuddy desktop client and sign in again using the same account and region." : "打开官方 WorkBuddy 桌面客户端，用相同账号和区域重新登录。"}</li>
        <li>{en ? "Confirm that the chosen model is available to your account. Text-only models cannot verify audio/video." : "确认账号有权使用所选模型；纯文本模型不能核验音频或视频。"}</li>
        <li>{en ? "Return and retry. If the desktop works but CLI still fails, collect the task log and check vendor authentication settings." : "返回并重试任务。如果桌面可用但 CLI 仍失败，请收集任务日志并检查厂商认证配置。"}</li>
      </ol>
      {message ? <p role="status">{message}</p> : null}
      {error ? <p className="field-error" role="alert">{error}</p> : null}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" disabled={busy} onClick={() => void perform(true)}><RefreshCw size={14} />{en ? "Recheck CLI" : "重新检测 CLI"}</button>
        <button type="button" className="button button-primary" disabled={busy} onClick={() => void perform(false)}><ExternalLink size={14} />{en ? "Open WorkBuddy" : "打开 WorkBuddy"}</button>
      </div>
    </div>
  </div>;
}
