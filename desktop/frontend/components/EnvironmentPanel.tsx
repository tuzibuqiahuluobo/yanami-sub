"use client";

import { Check, CircleAlert, Download, LoaderCircle, Play, RotateCcw } from "lucide-react";

import { isUsable, requiredResources } from "@/lib/resources";
import type { ResourceInstallSnapshot, ResourceStatus } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";


interface EnvironmentPanelProps {
  resources: ResourceStatus[];
  installs: ResourceInstallSnapshot[];
  submitting: string[];
  busy?: boolean;
  onInstall: (resourceId: string) => void;
}


export function EnvironmentPanel({
  resources,
  installs,
  submitting,
  busy,
  onInstall,
}: EnvironmentPanelProps) {
  const { t } = useLanguage();
  // Only what can block a task. Optional rows are excluded from the list as
  // well as the count: this panel answers "is anything standing in my way?",
  // and the model weights -- the one optional resource -- never are. Listing
  // them here also put a one-click 3.4GB download on the page, without the
  // size confirmation the resources page asks for. That page owns them.
  const required = requiredResources(resources);
  // An outdated tool counts as ready here: it works, and the count answers
  // "can I run something?", not "is everything at its newest version?".
  const ready = required.filter((resource) => isUsable(resource) && !submitting.includes(resource.id) &&
    !installs.some((install) => install.resource_id === resource.id &&
      (install.state === "queued" || install.state === "running"))).length;

  const resourceNames: Record<string, string> = {
    uv: t.newTask.env.uv,
    ffmpeg: t.newTask.env.ffmpeg,
    git: t.newTask.env.git,
    "yt-dlp": t.newTask.env.ytDlp,
  };

  return (
    <section className="environment-panel" aria-labelledby="environment-title">
      <div className="section-heading compact">
        <div>
          <p className="section-kicker">{t.newTask.env.kicker}</p>
          <h2 id="environment-title">{t.newTask.env.title}</h2>
        </div>
        <span className="section-count">
          {ready}/{required.length || 2} {t.newTask.env.readyCount}
        </span>
      </div>
      <div className="resource-list">
        {required.map((resource) => {
          const install = installs.find((item) => item.resource_id === resource.id);
          const isSubmitting = submitting.includes(resource.id);
          const activeInstall = install?.state === "queued" || install?.state === "running";
          const isBusy = isSubmitting || activeInstall || resource.state === "downloading";
          const isReady = !isBusy && isUsable(resource);
          const isPaused = !isBusy && install?.state === "paused";
          const isFailed = !isBusy && (install?.state === "failed" || resource.state === "failed");
          const status = !isSubmitting && activeInstall ? install.message : t.newTask.env.downloading;
          const percent = !isSubmitting && activeInstall && install.phase === "downloading" && install.total > 0
            ? Math.min(100, Math.max(0, Math.round(install.downloaded / install.total * 100))) : null;
          return (
            <div className="resource-row" key={resource.id}>
              <span
                className={`resource-state ${
                  isReady ? "is-ready" : isBusy ? "is-busy" : "is-missing"
                }`}
              >
                {isReady ? (
                  <Check size={13} />
                ) : isBusy ? (
                  <LoaderCircle size={13} className="spin" />
                ) : (
                  <CircleAlert size={13} />
                )}
              </span>
              <div>
                <strong>{resourceNames[resource.id] ?? resource.id}</strong>
                <span>
                  {isReady
                    ? // What is on disk, not the manifest's target: for an
                      // outdated tool the two differ, and "installed" next to
                      // a version nobody has installed yet is a false claim.
                      `${resource.installed_version || resource.version} · ${t.newTask.env.installed}`
                    : isBusy ? status
                      : isFailed ? (install?.error || resource.detail || t.resources.status.failed)
                        : isPaused ? t.resources.status.paused : t.newTask.env.willDownload}
                </span>
              </div>
              {!isReady ? (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`${isBusy ? status : isPaused || isFailed ? t.resources.actions.continueDownload : t.newTask.env.install} ${resourceNames[resource.id] ?? resource.id}${percent === null ? "" : ` ${percent}%`}`}
                  disabled={busy || isBusy}
                  onClick={() => onInstall(resource.id)}
                >
                  {percent !== null ? <svg className="environment-progress" viewBox="0 0 24 24" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" pathLength="100" className="environment-progress-track" />
                    <circle cx="12" cy="12" r="9" pathLength="100" className="environment-progress-value" style={{ strokeDashoffset: 100 - percent }} />
                  </svg> : isBusy ? <LoaderCircle size={15} className="spin" /> : isPaused ? <Play size={15} /> : isFailed ? <RotateCcw size={15} /> : <Download size={15} />}
                </button>
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="resource-footnote">
        {t.newTask.env.footnote}
      </p>
    </section>
  );
}
