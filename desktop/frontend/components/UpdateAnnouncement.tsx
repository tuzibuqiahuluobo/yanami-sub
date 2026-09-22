"use client";

import {
  ChevronDown,
  Download,
  ExternalLink,
  History,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { formatBytes } from "@/lib/formatters";
import type { UpdateCheck } from "@/lib/types";
import { updateHistoryFor } from "@/lib/updateHistory";

import { useLanguage } from "./LanguageProvider";


interface UpdateAnnouncementProps {
  open: boolean;
  update: UpdateCheck | null;
  onClose: () => void;
  onDisableAnnouncements: () => void;
  onInstall: () => Promise<void>;
  onOpenUpdatePage: () => Promise<unknown>;
}


type NoteBlock =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };


function plainMarkdown(value: string): string {
  return value
    .replace(/\[([^\]]+)]\([^)]+\)/g, "$1")
    .replace(/\*\*/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}


function releaseNoteBlocks(source: string): NoteBlock[] {
  const blocks: NoteBlock[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];

  const flush = () => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: plainMarkdown(paragraph.join(" ")) });
      paragraph = [];
    }
    if (list.length > 0) {
      blocks.push({ kind: "list", items: list.map(plainMarkdown) });
      list = [];
    }
  };

  for (const rawLine of source.replace(/\r/g, "").split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      flush();
      continue;
    }
    if (line.startsWith("# ")) {
      // The dialog header already names the release.
      continue;
    }
    if (line.startsWith("## ") || line.startsWith("### ")) {
      flush();
      blocks.push({
        kind: "heading",
        text: plainMarkdown(line.replace(/^#{2,3}\s+/, "")),
      });
      continue;
    }
    if (line.startsWith("- ")) {
      if (paragraph.length > 0) flush();
      list.push(line.slice(2));
      continue;
    }
    if (list.length > 0) {
      list[list.length - 1] = `${list[list.length - 1]} ${line}`;
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}


function ReleaseNotes({ source }: { source: string }) {
  const blocks = useMemo(() => releaseNoteBlocks(source), [source]);
  return (
    <div className="update-announcement-notes">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return <h3 key={`${block.kind}-${index}`}>{block.text}</h3>;
        }
        if (block.kind === "list") {
          return (
            <ul key={`${block.kind}-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${itemIndex}-${item}`}>{item}</li>
              ))}
            </ul>
          );
        }
        return <p key={`${block.kind}-${index}`}>{block.text}</p>;
      })}
    </div>
  );
}


export function UpdateAnnouncement({
  open,
  update,
  onClose,
  onDisableAnnouncements,
  onInstall,
  onOpenUpdatePage,
}: UpdateAnnouncementProps) {
  const { language, t } = useLanguage();
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [busy, setBusy] = useState<"install" | "github" | "">("");
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);
  const history = useMemo(() => updateHistoryFor(language), [language]);

  useEffect(() => {
    if (!open) return;
    setHistoryLoaded(false);
    setBusy("");
    setError("");
    closeRef.current?.focus();
    const scroller = document.querySelector<HTMLElement>(".workspace");
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    if (scroller) scroller.style.overflowY = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (scroller) scroller.style.overflowY = "";
    };
  }, [open, onClose, update?.version]);

  if (!open || !update?.available) return null;

  const kind = update.kind === "full"
    ? t.settings.updates.full
    : t.settings.updates.patch;
  const summary = update.size
    ? `${kind} · ${formatBytes(update.size)}`
    : kind;

  const install = async () => {
    setBusy("install");
    setError("");
    try {
      await onInstall();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : t.settings.updates.announcementFailed,
      );
      setBusy("");
    }
  };

  const openGitHub = async () => {
    setBusy("github");
    setError("");
    try {
      await onOpenUpdatePage();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : t.settings.updates.announcementOpenFailed,
      );
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="dialog-overlay update-announcement-overlay" onClick={onClose}>
      <section
        className="update-announcement-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="update-announcement-title"
        aria-describedby="update-announcement-summary"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="update-announcement-header">
          <span className="update-announcement-icon" aria-hidden="true">
            <Download size={21} />
          </span>
          <div>
            <span className="update-announcement-eyebrow">
              {t.settings.updates.announcementEyebrow}
            </span>
            <h2 id="update-announcement-title">
              {t.settings.updates.announcementTitle.replace("{version}", update.version)}
            </h2>
            <p id="update-announcement-summary">{summary}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="update-announcement-close"
            aria-label={t.settings.updates.announcementClose}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>

        <div className="update-announcement-scroll">
          <section className="update-announcement-current">
            <span>{t.settings.updates.announcementCurrent}</span>
            {update.releaseNotes ? (
              <ReleaseNotes source={update.releaseNotes} />
            ) : (
              <p>{t.settings.updates.announcementNoNotes}</p>
            )}
          </section>

          <section className="update-announcement-history">
            <button
              type="button"
              className="update-history-toggle"
              aria-expanded={historyLoaded}
              aria-controls="update-history-content"
              onClick={() => setHistoryLoaded((value) => !value)}
            >
              <History size={16} />
              <span>
                {historyLoaded
                  ? t.settings.updates.announcementHideHistory
                  : t.settings.updates.announcementLoadHistory.replace(
                      "{count}",
                      String(history.length),
                    )}
              </span>
              <ChevronDown size={16} className={historyLoaded ? "is-open" : ""} />
            </button>
            {historyLoaded ? (
              <div id="update-history-content" className="update-history-list">
                {history.map((entry) => (
                  <article key={entry.version} className="update-history-entry">
                    <span>{entry.version}</span>
                    <h3>{entry.title}</h3>
                    <ul>
                      {entry.notes.map((note) => <li key={note}>{note}</li>)}
                    </ul>
                  </article>
                ))}
              </div>
            ) : null}
          </section>

          <aside className="update-announcement-fallback">
            <ShieldCheck size={17} />
            <div>
              <strong>{t.settings.updates.announcementRecommended}</strong>
              <p>{t.settings.updates.announcementFallback}</p>
            </div>
            <button
              type="button"
              className="button button-secondary button-compact"
              disabled={busy !== ""}
              onClick={() => void openGitHub()}
            >
              <ExternalLink size={14} />
              {t.settings.updates.announcementGitHub}
            </button>
          </aside>

          {error ? (
            <p className="update-announcement-error" role="alert">{error}</p>
          ) : null}
        </div>

        <footer className="update-announcement-footer">
          <button
            type="button"
            className="update-announcement-disable"
            disabled={busy !== ""}
            onClick={onDisableAnnouncements}
          >
            <strong>{t.settings.updates.announcementDisable}</strong>
            <small>{t.settings.updates.announcementDisableHint}</small>
          </button>
          <div>
            <button
              type="button"
              className="button button-secondary"
              disabled={busy !== ""}
              onClick={onClose}
            >
              {t.settings.updates.announcementLater}
            </button>
            <button
              type="button"
              className="button button-primary"
              disabled={busy !== "" || !update.kind}
              onClick={() => void install()}
            >
              <Download size={15} className={busy === "install" ? "pulse" : ""} />
              {busy === "install"
                ? t.settings.updates.announcementStarting
                : t.settings.updates.announcementInstall}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
