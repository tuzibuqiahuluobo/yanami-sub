"use client";

import type { CSSProperties } from "react";
import {
  Boxes,
  BookOpenText,
  Clock3,
  ListChecks,
  Plus,
  Settings2,
  Download,
} from "lucide-react";

import { isInstallActive } from "@/lib/resources";
import type {
  CapabilityState,
  ResourceInstallSnapshot,
  Route,
} from "@/lib/types";

import { useLanguage } from "./LanguageProvider";


interface SidebarProps {
  route: Route;
  capabilities: CapabilityState;
  resourceInstalls: ResourceInstallSnapshot[];
  appVersion: string;
  /** The startup check found a release; the settings page has the details. */
  updateAvailable: boolean;
  onNavigate: (route: Route) => void;
}


export function Sidebar({
  route,
  capabilities,
  resourceInstalls,
  appVersion,
  updateAvailable,
  onNavigate,
}: SidebarProps) {
  const { t } = useLanguage();

  const navigation: Array<{
    route: Route;
    label: string;
    icon: typeof Plus;
  }> = [
    { route: "new-task", label: t.sidebar.newTask, icon: Plus },
    { route: "batch", label: t.sidebar.batch, icon: ListChecks },
    { route: "history", label: t.sidebar.history, icon: Clock3 },
    { route: "knowledge", label: t.sidebar.knowledge, icon: BookOpenText },
    { route: "resources", label: t.sidebar.resources, icon: Boxes },
    { route: "settings", label: t.sidebar.settings, icon: Settings2 },
  ];
  const activeIndex = Math.max(
    0,
    navigation.findIndex((item) => item.route === route),
  );

  const activeInstalls = resourceInstalls.filter(isInstallActive);
  const activeInstall = activeInstalls[0];
  const activeTotal = activeInstalls.reduce(
    (total, install) => total + install.total,
    0,
  );
  const activeDownloaded = activeInstalls.reduce(
    (total, install) => total + Math.min(install.downloaded, install.total),
    0,
  );
  const activePercent =
    activeInstall && activeTotal > 0
      ? Math.min(
          100,
          Math.round((activeDownloaded / activeTotal) * 100),
        )
      : null;
  return (
    <aside className="sidebar">
      <nav
        className="sidebar-nav"
        aria-label={t.sidebar.navigationAria}
        style={{ "--active-index": activeIndex } as CSSProperties}
      >
        <span className="nav-active-pill" aria-hidden="true" />
        {navigation.map((item) => {
          const Icon = item.icon;
          const active = route === item.route;
          return (
            <button
              type="button"
              key={item.route}
              className={`nav-item${active ? " is-active" : ""}`}
              aria-current={active ? "page" : undefined}
              onClick={() => onNavigate(item.route)}
            >
              <Icon size={16} strokeWidth={1.8} />
              <span>{item.label}</span>
              {item.route === "settings" && updateAvailable ? (
                <span
                  className="nav-dot"
                  title={t.sidebar.updateAvailable}
                  aria-label={t.sidebar.updateAvailable}
                />
              ) : null}
            </button>
          );
        })}
      </nav>

      <div className="sidebar-meta">
        {activeInstall ? (
          <button
            type="button"
            className="sidebar-download-status"
            onClick={() => onNavigate("resources")}
          >
            <Download size={14} />
            <span>
              <strong>
                {activeInstalls.length > 1
                  ? t.sidebar.resourcesProcessing.replace(
                    "{count}",
                    String(activeInstalls.length),
                  )
                  : t.sidebar.resourceProcessing}
              </strong>
              <small>
                {activeInstalls.length > 1
                  ? activePercent === null
                    ? t.sidebar.parallelDownloads
                    : `${activePercent}% · ${t.sidebar.parallelDownloads}`
                  : activePercent === null
                  ? activeInstall.message
                  : `${activePercent}% · ${activeInstall.message}`}
              </small>
            </span>
          </button>
        ) : null}
        <div className="sidebar-capability">
          <span
            className={`status-dot ${
              capabilities.translation ? "is-ready" : "is-neutral"
            }`}
          />
          <div>
            <strong>
              {capabilities.translation ? t.sidebar.translationReady : t.sidebar.localOnly}
            </strong>
            <span>
              {capabilities.translation
                ? t.sidebar.geminiConnected
                : t.sidebar.translationOptional}
            </span>
          </div>
        </div>
        <div className="sidebar-version">
          <span>Yanami Sub v{appVersion}</span>
        </div>
      </div>
    </aside>
  );
}
