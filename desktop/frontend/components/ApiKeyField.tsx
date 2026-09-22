"use client";

import {
  Check,
  CircleHelp,
  ExternalLink,
  Eye,
  EyeOff,
  KeyRound,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { useLanguage } from "./LanguageProvider";
import { useToast } from "./ToastProvider";


interface ApiKeyFieldProps {
  label: string;
  description: string;
  status: "configured" | "missing";
  placeholder: string;
  onSave: (value: string) => Promise<void>;
  onDelete: () => Promise<void>;
  guide?: {
    url: string;
    eyebrow: string;
    title: string;
    intro: string;
    steps: readonly string[];
  };
  onOpenOfficial?: (url: string) => Promise<unknown>;
}


export function ApiKeyField({
  label,
  description,
  status,
  placeholder,
  onSave,
  onDelete,
  guide,
  onOpenOfficial,
}: ApiKeyFieldProps) {
  const { t } = useLanguage();
  const { showSuccess } = useToast();
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [openingOfficial, setOpeningOfficial] = useState(false);
  const guideTitleId = useId();
  // A rejected save used to show nothing at all: the handlers had a
  // `finally` but no `catch`, so `invalid_api_keys` became an unhandled
  // rejection in a file:// WebView. The button flickered, the chip still
  // said "not configured", and the natural conclusion was that it saved.
  const [failure, setFailure] = useState("");

  useEffect(() => {
    if (!guideOpen) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setGuideOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [guideOpen]);

  const openOfficial = async () => {
    if (!guide || !onOpenOfficial) {
      return;
    }
    setOpeningOfficial(true);
    setFailure("");
    try {
      await onOpenOfficial(guide.url);
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : t.settings.translation.guideOpenError,
      );
    } finally {
      setOpeningOfficial(false);
    }
  };

  return (
    <div className="api-key-row">
      <div className="api-key-heading">
        <span className="api-key-icon">
          <KeyRound size={15} />
        </span>
        <div>
          <strong>{label}</strong>
          <span>{description}</span>
        </div>
        <span className={`key-status ${status === "configured" ? "is-ready" : ""}`}>
          {status === "configured" ? (
            <>
              <Check size={11} /> {t.apiKey.configured}
            </>
          ) : (
            t.apiKey.missing
          )}
        </span>
      </div>
      <div className="api-key-controls">
        <div className="secret-input">
          <input
            type={visible ? "text" : "password"}
            value={value}
            placeholder={
              status === "configured" ? t.apiKey.replace : placeholder
            }
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setValue(event.target.value)}
          />
          <button
            type="button"
            aria-label={visible ? t.apiKey.hide : t.apiKey.show}
            onClick={() => setVisible((shown) => !shown)}
          >
            {visible ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        {status === "configured" ? (
          <button
            type="button"
            className="icon-button danger"
            aria-label={`${t.apiKey.delete} ${label}`}
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              setFailure("");
              try {
                await onDelete();
                setValue("");
                showSuccess(`${label} ${t.toast.deleted}`, `api-key-delete-${label}`);
              } catch (error) {
                setFailure(
                  error instanceof Error ? error.message : t.apiKey.failed,
                );
              } finally {
                setSaving(false);
              }
            }}
          >
            <Trash2 size={14} />
          </button>
        ) : null}
        <button
          type="button"
          className="button button-secondary button-compact"
          disabled={!value.trim() || saving}
          onClick={async () => {
            setSaving(true);
            setFailure("");
            try {
              await onSave(value);
              setValue("");
              showSuccess(`${label} ${t.toast.saved}`, `api-key-save-${label}`);
            } catch (error) {
              setFailure(
                error instanceof Error ? error.message : t.apiKey.failed,
              );
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? t.apiKey.saving : t.apiKey.save}
        </button>
        {guide && onOpenOfficial ? (
          <>
            <button
              type="button"
              className="api-key-link"
              disabled={openingOfficial}
              onClick={() => void openOfficial()}
            >
              <ExternalLink size={13} />
              {t.settings.translation.getKey}
            </button>
            <button
              type="button"
              className="api-key-guide-help"
              aria-label={`${label} ${t.settings.translation.guideTooltip}`}
              data-tooltip={t.settings.translation.guideTooltip}
              onClick={() => setGuideOpen(true)}
            >
              <CircleHelp size={15} />
            </button>
          </>
        ) : null}
      </div>
      {failure ? (
        <p className="api-key-error" role="alert">
          {failure}
        </p>
      ) : null}
      {guideOpen && guide
        ? createPortal(
            <div
              className="dialog-overlay key-guide-overlay"
              role="presentation"
              onMouseDown={(event) => {
                if (event.currentTarget === event.target) {
                  setGuideOpen(false);
                }
              }}
            >
              <section
                className="dialog-card key-guide-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby={guideTitleId}
              >
                <header className="key-guide-header">
                  <span className="key-guide-mark">
                    <KeyRound size={18} />
                  </span>
                  <div>
                    <span className="key-guide-eyebrow">{guide.eyebrow}</span>
                    <h3 id={guideTitleId}>{guide.title}</h3>
                  </div>
                  <button
                    type="button"
                    className="key-guide-close"
                    aria-label={t.titleBar.close}
                    onClick={() => setGuideOpen(false)}
                  >
                    <X size={17} />
                  </button>
                </header>
                <p className="key-guide-intro">{guide.intro}</p>
                <ol className="key-guide-steps">
                  {guide.steps.map((step, index) => (
                    <li key={step}>
                      <span>{index + 1}</span>
                      <p>{step}</p>
                    </li>
                  ))}
                </ol>
                <div className="key-guide-safety">
                  <ShieldCheck size={15} />
                  <span>{t.settings.translation.guideSafety}</span>
                </div>
                <div className="dialog-actions key-guide-actions">
                  <button
                    type="button"
                    className="button button-secondary"
                    onClick={() => setGuideOpen(false)}
                  >
                    {t.settings.translation.guideClose}
                  </button>
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={openingOfficial}
                    onClick={() => void openOfficial()}
                  >
                    <ExternalLink size={14} />
                    {t.settings.translation.guideOpen}
                  </button>
                </div>
              </section>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
