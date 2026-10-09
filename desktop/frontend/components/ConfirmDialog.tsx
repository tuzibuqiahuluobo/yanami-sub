"use client";

import { useCallback, useEffect, useState, useRef, useId } from "react";
import { ShieldAlert } from "lucide-react";

import { saveUi, uiValue } from "@/lib/preferences";
import { useLanguage } from "./LanguageProvider";


export interface ConfirmDialogConfig {
  id: string;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  allowRemember?: boolean;
  tone?: "danger";
}

interface ConfirmDialogProps {
  config: ConfirmDialogConfig;
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}


// One array rather than a key per dialog: listing them used to mean scanning
// every localStorage key for a prefix.
function dismissed(): string[] {
  const value = uiValue<unknown>("dismissedConfirms", []);
  return Array.isArray(value) ? value.filter((id): id is string => typeof id === "string") : [];
}

export function isConfirmRemembered(id: string): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return dismissed().includes(id);
}

export function clearConfirmMemory(id: string): void {
  saveUi({ dismissedConfirms: dismissed().filter((entry) => entry !== id) });
}

export function listRememberedConfirms(): string[] {
  return dismissed();
}


export function ConfirmDialog({
  config,
  open,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const { t } = useLanguage();
  const [remember, setRemember] = useState(false);
  const card = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    setRemember(false);
    const previous = document.activeElement as HTMLElement | null;
    card.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onCancel(); }
      if (event.key !== "Tab") return;
      const controls = Array.from(card.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") || []);
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); previous?.focus(); };
  }, [open, onCancel]);

  // A modal has to own the scroll wheel. Without this the form underneath kept
  // scrolling while the dialog was up, so the page could move out from behind
  // a question the user had not answered yet.
  //
  // The scroller is `.workspace`, not `body`: the shell is a fixed grid with
  // `overflow: hidden` and the workspace pane is the thing that actually
  // scrolls, so locking `body` alone would do nothing here.
  useEffect(() => {
    if (!open) {
      return;
    }
    const scroller = document.querySelector<HTMLElement>(".workspace");
    if (!scroller) {
      return;
    }
    scroller.style.overflowY = "hidden";
    return () => {
      scroller.style.overflowY = "";
    };
  }, [open]);

  const handleConfirm = useCallback(() => {
    if (config.allowRemember !== false && remember && !isConfirmRemembered(config.id)) {
      saveUi({ dismissedConfirms: [...dismissed(), config.id] });
    }
    onConfirm();
  }, [remember, config.id, config.allowRemember, onConfirm]);

  if (!open) {
    return null;
  }

  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div ref={card} className={`dialog-card ${config.tone === "danger" ? "knowledge-confirm-danger" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} onClick={(e) => e.stopPropagation()}>
        {config.tone === "danger" ? <div className="knowledge-confirm-icon"><ShieldAlert size={24} /></div> : null}
        <h3 id={titleId}>{config.title}</h3>
        <p>{config.message}</p>
        {config.allowRemember !== false ? <label className="dialog-remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          {t.confirm.remember}
        </label> : null}
        <div className="dialog-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={onCancel}
          >
            {config.cancelLabel ?? t.confirm.cancel}
          </button>
          <button
            type="button"
            className="button button-primary"
            onClick={handleConfirm}
          >
            {config.confirmLabel ?? t.confirm.confirm}
          </button>
        </div>
      </div>
    </div>
  );
}
