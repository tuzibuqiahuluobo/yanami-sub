"use client";

import { useCallback, useEffect, useState } from "react";

import { saveUi, uiValue } from "@/lib/preferences";
import { useLanguage } from "./LanguageProvider";


export interface ConfirmDialogConfig {
  id: string;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
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
    if (remember && !isConfirmRemembered(config.id)) {
      saveUi({ dismissedConfirms: [...dismissed(), config.id] });
    }
    onConfirm();
  }, [remember, config.id, onConfirm]);

  if (!open) {
    return null;
  }

  return (
    <div className="dialog-overlay" onClick={onCancel}>
      <div className="dialog-card" onClick={(e) => e.stopPropagation()}>
        <h3>{config.title}</h3>
        <p>{config.message}</p>
        <label className="dialog-remember">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          {t.confirm.remember}
        </label>
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
