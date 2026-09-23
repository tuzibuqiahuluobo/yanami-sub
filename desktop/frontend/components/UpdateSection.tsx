"use client";

import { ExternalLink, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { formatBytes } from "@/lib/formatters";
import type { UpdateCheck, UpdateInstallSnapshot } from "@/lib/types";

import { useLanguage } from "./LanguageProvider";


export interface UpdateSectionProps {
  /** What the automatic startup check found, when it ran and found something. */
  startupUpdate: UpdateCheck | null;
  onCheckUpdates: () => Promise<UpdateCheck>;
  onInstallUpdate: (
    kind: "app" | "full",
    version: string,
  ) => Promise<UpdateInstallSnapshot>;
  updateInstall: UpdateInstallSnapshot | null;
  onCloseWindow: () => Promise<unknown>;
  onRestartApplication: () => Promise<unknown>;
  onOpenUpdatePage: () => Promise<unknown>;
  autoCheck: boolean;
  onAutoCheckChange: (enabled: boolean) => void;
}

/**
 * The settings page's update panel: what is available, what is downloading,
 * and the one switch that decides whether we look on startup.
 *
 * Download state is controlled by the app root so its compact progress card
 * survives navigation; this panel keeps the actionable restart/retry controls.
 */
export function UpdateSection({
  startupUpdate,
  onCheckUpdates,
  onInstallUpdate,
  updateInstall: install,
  onCloseWindow,
  onRestartApplication,
  onOpenUpdatePage,
  autoCheck,
  onAutoCheckChange,
}: UpdateSectionProps) {
  const { t } = useLanguage();
  const [updateMessage, setUpdateMessage] = useState("");
  const [availableUpdate, setAvailableUpdate] = useState<UpdateCheck | null>(
    startupUpdate,
  );
  // The startup check can land after this page is already open -- the initial
  // state above would miss it, and the sidebar dot would be pointing at a
  // panel that says nothing. `?? startupUpdate` so a manual check the user
  // just ran is not overwritten by it.
  useEffect(() => {
    if (startupUpdate !== null) {
      setAvailableUpdate((current) => current ?? startupUpdate);
    }
  }, [startupUpdate]);
  const [updateBusy, setUpdateBusy] = useState(false);
  return (
    <section className="settings-section update-section">
      <div className="update-content">
        <h2>{t.settings.updates.title}</h2>
        <p>{t.settings.updates.description}</p>
        {availableUpdate?.available && availableUpdate.releaseNotes ? (
          <p className="update-notes">{availableUpdate.releaseNotes}</p>
        ) : null}
        {updateMessage ? <span className="update-message">{updateMessage}</span> : null}
      </div>
      {install?.state === "ready" || install?.state === "failed" ? (
        <div className="update-install" role="status" aria-live="polite">
          {install.state === "ready" ? (
            <span className="update-message">
              {install.exit_required
                ? t.settings.updates.exitRequired
                : t.settings.updates.restartRequired}
            </span>
          ) : null}
          {install.state === "failed" ? (
            <span className="update-message update-message-error">
              {t.settings.updates.installFailed.replace("{error}", install.error)}
            </span>
          ) : null}
        </div>
      ) : null}
      <div className="update-actions">
        {install?.state === "ready" ? (
          <button
            type="button"
            className="button button-primary"
            disabled={updateBusy}
            onClick={async () => {
              setUpdateBusy(true);
              setUpdateMessage("");
              try {
                if (install.exit_required) {
                  await onCloseWindow();
                } else {
                  await onRestartApplication();
                }
              } catch (error) {
                setUpdateMessage(
                  error instanceof Error
                    ? error.message
                    : t.settings.updates.restartFailed,
                );
                setUpdateBusy(false);
              }
            }}
          >
            <RefreshCw size={14} className={updateBusy ? "spin" : ""} />
            {install.exit_required
              ? t.settings.updates.exitNow
              : t.settings.updates.restartNow}
          </button>
        ) : null}
        {availableUpdate?.available &&
        availableUpdate.kind &&
        install?.state !== "ready" &&
        install?.state !== "running" &&
        install?.state !== "queued" ? (
          <button
            type="button"
            className="button button-primary"
            disabled={updateBusy}
            onClick={async () => {
              const kind = availableUpdate.kind;
              if (!kind) {
                return;
              }
              setUpdateBusy(true);
              setUpdateMessage("");
              try {
                await onInstallUpdate(kind, availableUpdate.version);
              } catch (error) {
                setUpdateMessage(
                  error instanceof Error ? error.message : "Unable to install update",
                );
              } finally {
                setUpdateBusy(false);
              }
            }}
          >
            <RefreshCw size={14} />
            {install?.state === "failed"
              ? t.settings.updates.retryInstall
              : t.settings.updates.install}
          </button>
        ) : null}
        {availableUpdate?.available && availableUpdate.kind ? (
          <button
            type="button"
            className="button button-secondary"
            disabled={updateBusy}
            onClick={async () => {
              setUpdateBusy(true);
              try {
                await onOpenUpdatePage();
                setUpdateMessage(t.settings.updates.openedInBrowser);
              } catch (error) {
                setUpdateMessage(
                  error instanceof Error ? error.message : "Unable to open download page",
                );
              } finally {
                setUpdateBusy(false);
              }
            }}
          >
            <ExternalLink size={14} />
            {t.settings.updates.openDownloadPage}
          </button>
        ) : null}
        <button
          type="button"
          className="button button-secondary"
          disabled={updateBusy}
          onClick={async () => {
            setUpdateBusy(true);
            setUpdateMessage(t.settings.updates.checking);
            try {
              const result = await onCheckUpdates();
              setAvailableUpdate(result);
              setUpdateMessage(
                result.available
                  ? t.settings.updates.available
                      .replace("{version}", result.version)
                      .replace(
                        "{kind}",
                        result.kind === "full"
                          ? t.settings.updates.full
                          : t.settings.updates.patch,
                      )
                      .replace("{size}", formatBytes(result.size))
                  : t.settings.updates.latest,
              );
            } catch (error) {
              setAvailableUpdate(null);
              setUpdateMessage(
                error instanceof Error
                  ? error.message
                  : t.settings.updates.noUpdateSource,
              );
            } finally {
              setUpdateBusy(false);
            }
          }}
        >
          <RefreshCw size={14} className={updateBusy ? "spin" : ""} />
          {t.settings.updates.checkUpdate}
        </button>
      </div>
      <label className="switch-row update-auto-check">
        <input
          type="checkbox"
          checked={autoCheck}
          onChange={(event) => onAutoCheckChange(event.target.checked)}
        />
        <span>
          <strong>{t.settings.updates.autoCheck}</strong>
          <small>{t.settings.updates.autoCheckHint}</small>
        </span>
      </label>
    </section>
  );
}
