"use client";

import type { ReactNode } from "react";

import type { AppState } from "@/lib/state";
import type { DesktopApi, LocalAgentStatus, Route } from "@/lib/types";

import { Sidebar } from "./Sidebar";
import { TitleBar } from "./TitleBar";


interface AppShellProps {
  state: AppState;
  agentStatuses: LocalAgentStatus[] | null;
  api: DesktopApi;
  onNavigate: (route: Route) => void;
  updateAvailable: boolean;
  children: ReactNode;
}


export function AppShell({
  state,
  agentStatuses,
  api,
  onNavigate,
  updateAvailable,
  children,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <TitleBar api={api} />
      <Sidebar
        route={state.route}
        capabilities={state.capabilities}
        geminiConfigured={state.settings.api_keys.gemini_free === "configured" || state.settings.api_keys.gemini_paid === "configured"}
        agentStatuses={agentStatuses}
        resourceInstalls={state.resourceInstalls}
        appVersion={state.appVersion}
        updateAvailable={updateAvailable}
        onNavigate={onNavigate}
      />
      <section className="workspace">
        <div className="workspace-view" key={state.route}>
          {children}
        </div>
      </section>
    </div>
  );
}
