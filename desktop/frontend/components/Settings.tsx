"use client";

import {
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  Github,
  Heart,
  Monitor,
  Moon,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Star,
  Sun,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  isStale,
  AUTOMATIC,
  readProcessingDevice,
  writeProcessingDevice,
  type ProcessingDevice,
} from "@/lib/processingDevice";
import { detectAvailableFonts } from "@/lib/fonts";
import { saveUi, uiValue } from "@/lib/preferences";
import type { AppState } from "@/lib/state";
import type {
  ApiProvider,
  KeyExportResult,
  LocalAgentStatus,
  RevealedApiKeys,
  RoutingUpdate,
  SharedSettings,
} from "@/lib/types";
import {
  DEFAULT_APPEARANCE,
  FONT_SCALE_LABELS,
  type AppearanceSettings,
  type FontScale,
  type ThemeMode,
} from "@/lib/useAppearance";
import { runInterfaceTransition } from "@/lib/viewTransition";

import { ApiKeyField } from "./ApiKeyField";
import { CustomSelect } from "./CustomSelect";
import { useLanguage } from "./LanguageProvider";
import { UpdateSection, type UpdateSectionProps } from "./UpdateSection";


/** The update panel keeps its own props; this page only passes them through. */
interface SettingsProps extends UpdateSectionProps {
  state: AppState;
  appearance: AppearanceSettings;
  onAppearanceChange: (changes: Partial<AppearanceSettings>) => void;
  onSaveKey: (
    provider: ApiProvider,
    value: string,
  ) => Promise<void>;
  onDeleteKey: (provider: ApiProvider) => Promise<void>;
  onRevealKeys: () => Promise<RevealedApiKeys>;
  onExportKeys: () => Promise<KeyExportResult>;
  onSaveRouting: (values: RoutingUpdate) => Promise<void>;
  onSaveProviderKey: (providerId: string, value: string) => Promise<void>;
  onDeleteProviderKey: (providerId: string) => Promise<void>;
  onProbeLocalAgents: () => Promise<LocalAgentStatus[]>;
  onSaveSharedSettings: (values: SharedSettings) => Promise<void>;
  onUseRawSubtitle: () => void;
  onRescanGpus: () => Promise<unknown>;
}

export function Settings({
  state,
  appearance: appearanceProp,
  onAppearanceChange,
  onSaveKey,
  onDeleteKey,
  onRevealKeys,
  onExportKeys,
  onSaveRouting,
  onSaveProviderKey,
  onDeleteProviderKey,
  onProbeLocalAgents,
  onSaveSharedSettings,
  onUseRawSubtitle,
  onRescanGpus,
  // Whatever is left is the update panel's, by construction: `SettingsProps`
  // adds its own props to `UpdateSectionProps` and this page reads none of them.
  ...update
}: SettingsProps) {
  const appearance = appearanceProp ?? DEFAULT_APPEARANCE;
  const [docsOpen, setDocsOpen] = useState(false);
  const [routingCatalogOpen, setRoutingCatalogOpen] = useState(false);
  // Preferences are hydrated before this page can be reached, so the initial
  // read is already the durable one.
  const [closeWindowAction, setCloseWindowAction] = useState(
    () => uiValue<string>("closeWindowAction", "minimize")
  );
  // One global choice rather than a per-task control: the cards in a machine
  // do not change between tasks. It rides along with each request because that
  // is the only channel the backend has.
  const [device, setDevice] = useState<ProcessingDevice>(readProcessingDevice);
  const gpus = state.gpus;
  const deviceValue =
    device.device === "cpu"
      ? "cpu"
      : device.gpuIndex === null
        ? "auto"
        : String(device.gpuIndex);
  const deviceStale = isStale(device, gpus);
  const selectDevice = (value: string) => {
    const index = Number(value);
    const choice: ProcessingDevice =
      value === "cpu"
        ? { device: "cpu", gpuIndex: null, gpuName: "" }
        : value === "auto"
          ? AUTOMATIC
          : {
              device: "cuda",
              gpuIndex: index,
              gpuName:
                gpus?.devices.find((gpu) => gpu.index === index)?.name ?? "",
            };
    writeProcessingDevice(choice);
    setDevice(choice);
  };
  // Saved keys stay off screen until asked for; masked even then. The panel
  // exists so keys can leave this Windows account *before* a machine switch.
  // The shared knob lives in config.toml, so the panel only mirrors it; the
  // dropdown value is the string form of the stored number ("" = not set).
  const storedScale = state.sharedSettings.split_length_scale;
  const [lengthChoice, setLengthChoice] = useState(
    storedScale === null || storedScale === undefined ? "" : String(storedScale),
  );
  const [lengthError, setLengthError] = useState(false);
  useEffect(() => {
    setLengthChoice(
      storedScale === null || storedScale === undefined
        ? ""
        : String(storedScale),
    );
  }, [storedScale]);
  const [revealed, setRevealed] = useState<RevealedApiKeys | null>(null);
  const [showFullKeys, setShowFullKeys] = useState(false);
  const [revealBusy, setRevealBusy] = useState(false);
  const [revealError, setRevealError] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportResult, setExportResult] = useState<KeyExportResult | null>(null);
  const [exportError, setExportError] = useState(false);
  const routing = state.routing;
  const toRoutingDraft = (): RoutingUpdate => ({
    preset: routing.active_preset_id || "default",
    execution_policy: routing.execution_policy || routing.policies[0] || "",
    local_agent_timeout_seconds: routing.local_agent_timeout_seconds,
    local_agent_allow_unisolated_user_config:
      routing.local_agent_allow_unisolated_user_config,
    local_agent_service_tier: routing.local_agent_service_tier,
    local_agent_reasoning_effort: routing.local_agent_reasoning_effort,
    local_agent_max_parallel: routing.local_agent_max_parallel,
  });
  const [routingDraft, setRoutingDraft] = useState<RoutingUpdate>(toRoutingDraft);
  const [routingBusy, setRoutingBusy] = useState(false);
  const [routingError, setRoutingError] = useState("");
  const [agentProbeBusy, setAgentProbeBusy] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState<LocalAgentStatus[] | null>(null);
  useEffect(() => {
    setRoutingDraft(toRoutingDraft());
  }, [routing]);
  const apiError = state.task.error?.code === "api_key_required";
  const { language, setLanguage, t } = useLanguage();
  const capability = {
    tone: state.capabilities.translation ? "success" : "neutral",
    title: state.capabilities.translation
      ? t.sidebar.translationReady
      : t.sidebar.localOnly,
  } as const;

  const fonts = useMemo(() => detectAvailableFonts(), []);
  const fontOptions = useMemo(
    () => [
      { value: "", label: t.settings.appearance.defaultFont },
      ...fonts.map((f) => ({ value: f, label: f })),
    ],
    [fonts, t],
  );

  const scaleOptions = useMemo(
    () =>
      (Object.keys(FONT_SCALE_LABELS) as FontScale[]).map((key) => ({
        value: key,
        label: t.settings.fontScale[key],
      })),
    [t],
  );

  const themeOptions: { value: ThemeMode; label: string; icon: typeof Sun }[] = [
    { value: "light", label: t.settings.theme.light, icon: Sun },
    { value: "dark", label: t.settings.theme.dark, icon: Moon },
    { value: "marisa", label: t.settings.theme.marisa, icon: Star },
    { value: "reimu", label: t.settings.theme.reimu, icon: Sparkles },
    { value: "yanami", label: t.settings.theme.yanami, icon: Heart },
    { value: "system", label: t.settings.theme.system, icon: Monitor },
  ];

  const selectTheme = (theme: ThemeMode) => {
    if (theme === appearance.theme) return;
    runInterfaceTransition(() => onAppearanceChange({ theme }));
  };

  const languageOptions = [
    { value: "zh", label: t.settings.language.zh },
    { value: "en", label: t.settings.language.en },
  ];
  const customProviders = routing.providers.filter((provider) => provider.key_env);

  return (
    <div className="page settings-page">
      <header className="page-header">
        <div>
          {/* <p className="page-kicker">{t.settings.kicker}</p> */}
          <h1>{t.settings.title}</h1>
          <p>{t.settings.description}</p>
        </div>
      </header>

      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>{t.settings.appearance.title}</h2>
            <p>{t.settings.appearance.description}</p>
          </div>
        </div>

        <div className="appearance-grid">
          <div className="appearance-item appearance-item-vertical">
            <span className="appearance-label">{t.settings.appearance.theme}</span>
            <div className="theme-switcher">
              {themeOptions.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  data-theme-option={value}
                  className={`theme-btn${appearance.theme === value ? " is-active" : ""}`}
                  onClick={() => selectTheme(value)}
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="appearance-item">
            <span className="appearance-label">{t.settings.appearance.fontFamily}</span>
            <CustomSelect
              value={appearance.fontFamily}
              ariaLabel={t.settings.appearance.fontFamily}
              onChange={(value) => onAppearanceChange({ fontFamily: value })}
              options={fontOptions}
            />
          </div>

          <div className="appearance-item">
            <span className="appearance-label">{t.settings.appearance.fontSize}</span>
            <CustomSelect
              value={appearance.fontScale}
              ariaLabel={t.settings.appearance.fontSize}
              onChange={(value) =>
                onAppearanceChange({ fontScale: value as FontScale })
              }
              options={scaleOptions}
            />
          </div>

          <div className="appearance-item">
            <span className="appearance-label">{t.settings.language.label}</span>
            <CustomSelect
              value={language}
              ariaLabel={t.settings.language.label}
              onChange={(value) => setLanguage(value as "zh" | "en")}
              options={languageOptions}
            />
          </div>

          <div className="appearance-item glass-opacity-item">
            <div className="glass-opacity-label">
              <span className="appearance-label">{t.settings.appearance.glassOpacity}</span>
              <small>{t.settings.appearance.glassOpacityHint}</small>
            </div>
            <div className="glass-opacity-control">
              <input
                type="range"
                min="40"
                max="100"
                step="1"
                value={appearance.glassOpacity}
                onChange={(e) => onAppearanceChange({ glassOpacity: Number(e.target.value) })}
                className="glass-opacity-slider"
              />
              <span className="glass-opacity-value">{appearance.glassOpacity}%</span>
            </div>
          </div>

          <div className="appearance-item motion-preference-item">
            <div className="motion-preference-copy">
              <span className="appearance-label">{t.settings.appearance.animations}</span>
              <small>{t.settings.appearance.animationsHint}</small>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={appearance.animations}
              aria-label={t.settings.appearance.animations}
              className={`motion-toggle${appearance.animations ? " is-on" : ""}`}
              onClick={() => onAppearanceChange({ animations: !appearance.animations })}
            >
              <span aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>{t.settings.device.title}</h2>
            <p>{t.settings.device.description}</p>
          </div>
          {/* Always reachable: a machine that had one card when the app
              started is exactly the one that needs a rescan after a second
              goes in. */}
          <button
            type="button"
            className="button button-secondary button-compact"
            onClick={() => void onRescanGpus()}
          >
            <RefreshCw size={14} />
            {t.settings.device.rescan}
          </button>
        </div>
        {gpus === undefined || gpus.state === "scanning" ? (
          <p className="device-note">{t.settings.device.scanning}</p>
        ) : gpus.devices.length > 1 ? (
          <div className="device-options">
            {[
              { value: "auto", label: t.settings.device.automatic },
              ...gpus.devices.map((gpu) => ({
                value: String(gpu.index),
                label: `GPU ${gpu.index}: ${gpu.name}`,
              })),
              { value: "cpu", label: t.settings.device.cpu },
            ].map(({ value, label }) => (
              <button
                key={value}
                type="button"
                className={`device-btn${deviceValue === value ? " is-active" : ""}`}
                onClick={() => selectDevice(value)}
              >
                {label}
              </button>
            ))}
          </div>
        ) : (
          // Nothing to choose between, so say what will be used rather than
          // offering a picker with one entry.
          <p className="device-single">
            {gpus.devices.length === 1
              ? `GPU 0: ${gpus.devices[0].name}`
              : t.settings.device.none}
          </p>
        )}
        {deviceStale ? (
          <p className="device-note">{t.settings.device.stale}</p>
        ) : null}
      </section>

      {apiError ? (
        <section className="settings-callout">
          <div className="callout-icon">
            <CircleHelp size={18} />
          </div>
          <div>
            <strong>{t.apiError.title}</strong>
            <p>{t.apiError.description}</p>
          </div>
          <button
            type="button"
            className="button button-secondary"
            onClick={onUseRawSubtitle}
          >
            <ArrowLeft size={14} />
            {t.apiError.rawSubtitleOnly}
          </button>
        </section>
      ) : null}

      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>{t.settings.translation.title}</h2>
            <p>{t.settings.translation.description}</p>
          </div>
          <span className={`capability-chip is-${capability.tone}`}>
            {capability.tone === "success" ? (
              <CheckCircle2 size={13} />
            ) : (
              <ShieldCheck size={13} />
            )}
            {capability.title}
          </span>
        </div>

        <div className="api-key-list">
          <ApiKeyField
            label="Gemini Free"
            description={t.settings.translation.geminiFree}
            placeholder={t.settings.translation.poolPlaceholder}
            status={state.settings.api_keys.gemini_free}
            onSave={(value) => onSaveKey("gemini_free", value)}
            onDelete={() => onDeleteKey("gemini_free")}
          />
          <ApiKeyField
            label="Gemini Paid"
            description={t.settings.translation.geminiPaid}
            placeholder={t.settings.translation.poolPlaceholder}
            status={state.settings.api_keys.gemini_paid}
            onSave={(value) => onSaveKey("gemini_paid", value)}
            onDelete={() => onDeleteKey("gemini_paid")}
          />
          <ApiKeyField
            label="Exa"
            description={t.settings.translation.exa}
            placeholder="exa-…"
            status={state.settings.api_keys.exa}
            onSave={(value) => onSaveKey("exa", value)}
            onDelete={() => onDeleteKey("exa")}
          />
          <ApiKeyField
            label="Tavily"
            description={t.settings.translation.tavily}
            placeholder="tvly-…"
            status={state.settings.api_keys.tavily}
            onSave={(value) => onSaveKey("tavily", value)}
            onDelete={() => onDeleteKey("tavily")}
          />
        </div>

        <div className="api-key-reveal">
          {revealed === null ? (
            <button
              type="button"
              className="button button-secondary button-compact"
              disabled={revealBusy}
              onClick={async () => {
                setRevealBusy(true);
                setRevealError(false);
                try {
                  setRevealed(await onRevealKeys());
                } catch {
                  setRevealError(true);
                } finally {
                  setRevealBusy(false);
                }
              }}
            >
              <Eye size={14} /> {t.settings.translation.reveal}
            </button>
          ) : (
            <>
              <div className="revealed-keys">
                {(["gemini_free", "gemini_paid", "exa", "tavily"] as const).map((provider) => {
                  const entries = revealed[provider] ?? [];
                  if (entries.length === 0) {
                    return null;
                  }
                  const labels = {
                    gemini_free: "Gemini Free",
                    gemini_paid: "Gemini Paid",
                    exa: "Exa",
                    tavily: "Tavily",
                  } as const;
                  return (
                    <div key={provider} className="revealed-provider">
                      <strong>{labels[provider]}</strong>
                      <ul>
                        {entries.map((entry, index) => (
                          <li key={`${provider}-${index}`}>
                            {entry.name ? <span>{entry.name}</span> : null}
                            <code>
                              {showFullKeys ? entry.key : entry.masked}
                            </code>
                          </li>
                        ))}
                      </ul>
                    </div>
                  );
                })}
                {(["gemini_free", "gemini_paid", "exa", "tavily"] as const).every(
                  (provider) => (revealed[provider] ?? []).length === 0,
                ) ? (
                  <p>{t.settings.translation.revealEmpty}</p>
                ) : null}
              </div>
              <div className="revealed-actions">
                <button
                  type="button"
                  className="button button-secondary button-compact"
                  onClick={() => setShowFullKeys((shown) => !shown)}
                >
                  {showFullKeys ? <EyeOff size={14} /> : <Eye size={14} />}
                  {showFullKeys
                    ? t.settings.translation.revealMask
                    : t.settings.translation.revealShowFull}
                </button>
                <button
                  type="button"
                  className="button button-secondary button-compact"
                  onClick={() => {
                    setRevealed(null);
                    setShowFullKeys(false);
                  }}
                >
                  {t.settings.translation.revealHide}
                </button>
              </div>
              <p className="revealed-note">{t.settings.translation.revealNote}</p>
            </>
          )}
          {revealError ? (
            <p className="revealed-error">{t.settings.translation.revealError}</p>
          ) : null}
          <div className="api-key-export">
            <button
              type="button"
              className="button button-secondary button-compact"
              disabled={exportBusy}
              onClick={async () => {
                setExportBusy(true);
                setExportError(false);
                setExportResult(null);
                try {
                  const result = await onExportKeys();
                  if (!result.cancelled) setExportResult(result);
                } catch {
                  setExportError(true);
                } finally {
                  setExportBusy(false);
                }
              }}
            >
              <Download size={14} />
              {exportBusy
                ? t.settings.translation.exporting
                : t.settings.translation.export}
            </button>
            <p>{t.settings.translation.exportHint}</p>
          </div>
          {exportResult ? (
            <p className="revealed-note">
              {exportResult.count > 0 && exportResult.path
                ? t.settings.translation.exported
                    .replace("{count}", String(exportResult.count))
                    .replace("{path}", exportResult.path)
                : t.settings.translation.exportEmpty}
            </p>
          ) : null}
          {exportError ? (
            <p className="revealed-error">{t.settings.translation.exportError}</p>
          ) : null}
        </div>
      </section>

      <section className="settings-section routing-settings">
        <div className="settings-section-heading">
          <div>
            <h2>{t.settings.routing.title}</h2>
            <p>{t.settings.routing.description}</p>
          </div>
          <span className={`capability-chip is-${routing.local_agent_bound ? "success" : "neutral"}`}>
            {routing.local_agent_bound ? t.settings.routing.agentRoute : t.settings.routing.apiRoute}
          </span>
        </div>

        {routing.error ? (
          <p className="routing-error" role="alert">{routing.error}</p>
        ) : (
          <>
            <div className="routing-grid">
              <div className="field">
                <span>{t.settings.routing.preset}</span>
                <CustomSelect
                  value={routingDraft.preset}
                  ariaLabel={t.settings.routing.preset}
                  disabled={routingBusy}
                  onChange={(value) => setRoutingDraft((current) => ({ ...current, preset: value }))}
                  options={routing.presets.map((preset) => ({
                    value: preset.id,
                    label: `${preset.name} · ${preset.id}`,
                  }))}
                />
              </div>
              <div className="field">
                <span>{t.settings.routing.policy}</span>
                <CustomSelect
                  value={routingDraft.execution_policy}
                  ariaLabel={t.settings.routing.policy}
                  disabled={routingBusy}
                  onChange={(value) => setRoutingDraft((current) => ({ ...current, execution_policy: value }))}
                  options={routing.policies.map((policy) => ({ value: policy, label: policy }))}
                />
              </div>
              <div className="field">
                <span>{t.settings.routing.serviceTier}</span>
                <CustomSelect
                  value={routingDraft.local_agent_service_tier}
                  ariaLabel={t.settings.routing.serviceTier}
                  disabled={routingBusy}
                  onChange={(value) => setRoutingDraft((current) => ({
                    ...current,
                    local_agent_service_tier: value as RoutingUpdate["local_agent_service_tier"],
                  }))}
                  options={[
                    { value: "", label: t.settings.routing.followCore },
                    { value: "fast", label: "fast" },
                    { value: "flex", label: "flex" },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.settings.routing.reasoning}</span>
                <CustomSelect
                  value={routingDraft.local_agent_reasoning_effort}
                  ariaLabel={t.settings.routing.reasoning}
                  disabled={routingBusy}
                  onChange={(value) => setRoutingDraft((current) => ({
                    ...current,
                    local_agent_reasoning_effort: value as RoutingUpdate["local_agent_reasoning_effort"],
                  }))}
                  options={["", "low", "medium", "high", "xhigh"].map((value) => ({
                    value,
                    label: value || t.settings.routing.followCell,
                  }))}
                />
              </div>
              <label className="field">
                <span>{t.settings.routing.timeout}</span>
                <input
                  type="number"
                  min={10}
                  step={10}
                  disabled={routingBusy}
                  value={routingDraft.local_agent_timeout_seconds}
                  onChange={(event) => setRoutingDraft((current) => ({
                    ...current,
                    local_agent_timeout_seconds: Math.max(10, Number(event.target.value) || 10),
                  }))}
                />
              </label>
              <label className="field">
                <span>{t.settings.routing.parallel}</span>
                <input
                  type="number"
                  min={1}
                  step={1}
                  disabled={routingBusy}
                  value={routingDraft.local_agent_max_parallel}
                  onChange={(event) => setRoutingDraft((current) => ({
                    ...current,
                    local_agent_max_parallel: Math.max(1, Number(event.target.value) || 1),
                  }))}
                />
              </label>
            </div>

            <label className="switch-row routing-isolation">
              <input
                type="checkbox"
                checked={routingDraft.local_agent_allow_unisolated_user_config}
                disabled={routingBusy}
                onChange={(event) => setRoutingDraft((current) => ({
                  ...current,
                  local_agent_allow_unisolated_user_config: event.target.checked,
                }))}
              />
              <span>
                <strong>{t.settings.routing.unisolated}</strong>
                <small>{t.settings.routing.unisolatedHint}</small>
              </span>
            </label>

            <div className="routing-actions">
              <span>{t.settings.routing.configPath}: <code>{routing.config_path}</code></span>
              <button
                type="button"
                className="button button-primary button-compact"
                disabled={routingBusy || !routingDraft.preset || !routingDraft.execution_policy}
                onClick={async () => {
                  setRoutingBusy(true);
                  setRoutingError("");
                  try {
                    await onSaveRouting(routingDraft);
                  } catch (error) {
                    setRoutingError(error instanceof Error ? error.message : t.settings.routing.saveFailed);
                  } finally {
                    setRoutingBusy(false);
                  }
                }}
              >
                {routingBusy ? t.settings.routing.saving : t.settings.routing.save}
              </button>
            </div>
            {routingError ? <p className="routing-error" role="alert">{routingError}</p> : null}

            <div className={`routing-catalog${routingCatalogOpen ? " is-open" : ""}`}>
              <button
                type="button"
                className="routing-catalog-toggle"
                aria-expanded={routingCatalogOpen}
                aria-controls="routing-catalog-content"
                onClick={() => setRoutingCatalogOpen((open) => !open)}
              >
                <ChevronDown size={14} aria-hidden="true" />
                <span>{t.settings.routing.catalog.replace("{groups}", String(Object.keys(routing.model_groups).length)).replace("{targets}", String(routing.targets.length))}</span>
              </button>
              <div
                id="routing-catalog-content"
                className="routing-catalog-reveal"
                role="region"
                aria-hidden={!routingCatalogOpen}
              >
                <div className="routing-catalog-reveal-inner">
                  <div className="routing-catalog-columns">
                    <div>
                      <strong>{t.settings.routing.groups}</strong>
                      <ul>{Object.entries(routing.model_groups).map(([group, targets]) => <li key={group}><code>{group}</code><span>{targets.length}</span></li>)}</ul>
                    </div>
                    <div>
                      <strong>{t.settings.routing.targets}</strong>
                      <ul>{routing.targets.map((target) => <li key={target.id}><code>{target.id}</code><span>{target.provider_tier}</span></li>)}</ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="agent-diagnostics">
              <div className="settings-section-heading compact">
                <div>
                  <h3>{t.settings.routing.agents}</h3>
                  <p>{t.settings.routing.agentsHint}</p>
                </div>
                <button
                  type="button"
                  className="button button-secondary button-compact"
                  disabled={agentProbeBusy}
                  onClick={async () => {
                    setAgentProbeBusy(true);
                    setRoutingError("");
                    try {
                      setAgentStatuses(await onProbeLocalAgents());
                    } catch (error) {
                      setRoutingError(error instanceof Error ? error.message : t.settings.routing.probeFailed);
                    } finally {
                      setAgentProbeBusy(false);
                    }
                  }}
                >
                  <RefreshCw size={14} /> {agentProbeBusy ? t.settings.routing.probing : t.settings.routing.probe}
                </button>
              </div>
              {agentStatuses ? (
                <div className="agent-status-list">
                  {agentStatuses.map((agent) => (
                    <div className="agent-status-row" key={agent.provider_tier}>
                      <div><strong>{agent.provider_tier}</strong><small>{agent.driver || agent.models.join(", ")}</small></div>
                      <span className={`resource-label is-${agent.status === "ready" ? "ready" : agent.status === "missing" ? "neutral" : "failed"}`}>{t.settings.routing.agentStatus[agent.status]}</span>
                      <small title={agent.detail}>{agent.version || agent.detail}</small>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>

            {customProviders.length ? (
              <div className="custom-provider-keys">
                <h3>{t.settings.routing.customProviders}</h3>
                <p>{t.settings.routing.customProvidersHint}</p>
                <div className="api-key-list">
                  {customProviders.map((provider) => (
                    <ApiKeyField
                      key={provider.id}
                      label={provider.id}
                      description={`${provider.kind} · ${provider.base_url || provider.key_env}`}
                      placeholder={provider.key_env}
                      status={provider.configured ? "configured" : "missing"}
                      onSave={(value) => onSaveProviderKey(provider.id, value)}
                      onDelete={() => onDeleteProviderKey(provider.id)}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
      </section>

      <UpdateSection {...update} />

      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>{t.settings.confirmMemory.title}</h2>
            {/* <p>{t.settings.confirm-Memory.description}</p> */}
          </div>
        </div>
        <div className="confirm-memory-list">
          <div className="confirm-memory-row">
            <span className="confirm-memory-label">{t.settings.confirmMemory.closePanel}</span>
            <CustomSelect
              value={closeWindowAction}
              ariaLabel={t.settings.confirmMemory.closePanel}
              onChange={(value) => {
                const action = value || "minimize";
                saveUi({ closeWindowAction: action });
                setCloseWindowAction(action);
              }}
              options={[
                { value: "minimize", label: t.settings.confirmMemory.minimizeToTray },
                { value: "close", label: t.settings.confirmMemory.exitApp },
              ]}
            />
          </div>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>{t.settings.subtitleLength.title}</h2>
            <p>{t.settings.subtitleLength.description}</p>
          </div>
        </div>
        <div className="confirm-memory-list">
          <div className="confirm-memory-row">
            <span className="confirm-memory-label">
              {t.settings.subtitleLength.label}
            </span>
            <CustomSelect
              value={lengthChoice}
              onChange={async (value) => {
                const previous = lengthChoice;
                // Empty = not set: the key is removed from config.toml rather
                // than written as an explicit default, so a better default
                // still reaches this user later.
                const scale = value === "" ? null : Number(value);
                setLengthChoice(value);
                setLengthError(false);
                try {
                  await onSaveSharedSettings({ split_length_scale: scale });
                } catch {
                  setLengthChoice(previous);
                  setLengthError(true);
                }
              }}
              options={[
                { value: "0.8", label: t.settings.subtitleLength.shorter },
                { value: "", label: t.settings.subtitleLength.standard },
                { value: "1.3", label: t.settings.subtitleLength.longer },
              ]}
            />
          </div>
          <p className="settings-hint">
            {lengthError
              ? t.settings.subtitleLength.failed
              : `${t.settings.subtitleLength.savedTo}${
                  state.configPath ? `：${state.configPath}` : ""
                }`}
          </p>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <h2>{t.settings.acknowledgment.title}</h2>
            <p>{t.settings.acknowledgment.description}</p>
          </div>
        </div>
        <div className="acknowledgment-content">
          <div className="acknowledgment-item">
            <Github size={16} />
            <div className="acknowledgment-info">
              <span className="acknowledgment-label">{t.settings.acknowledgment.github}</span>
              <a
                href="https://github.com/tuzibuqiahuluobo/yanami-sub"
                target="_blank"
                rel="noopener noreferrer"
                className="acknowledgment-link"
              >
                tuzibuqiahuluobo/yanami-sub
                <ExternalLink size={12} />
              </a>
            </div>
          </div>
          <div className="acknowledgment-item">
            <Heart size={16} />
            <div className="acknowledgment-info">
              <span className="acknowledgment-label">{t.settings.acknowledgment.author}</span>
              <div className="acknowledgment-authors">
                <span className="acknowledgment-value">caca2331</span>
                <span className="acknowledgment-value">tuzibuqiahuluobo</span>
                <span className="acknowledgment-value">回不去的星光</span>
              </div>
            </div>
          </div>
          <div className="acknowledgment-item">
            <BookOpen size={16} />
            <div className="acknowledgment-info">
              <span className="acknowledgment-label">{t.settings.acknowledgment.documentation}</span>
              <button
                type="button"
                className="acknowledgment-link"
                onClick={() => setDocsOpen(true)}
              >
                {t.settings.acknowledgment.viewDocs}
                <BookOpen size={12} />
              </button>
            </div>
          </div>
        </div>
      </section>

      {docsOpen ? (
        <div className="dialog-overlay" onClick={() => setDocsOpen(false)}>
          <article
            className="dialog-card docs-dialog"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="docs-dialog-header">
              <div>
                <span className="eyebrow">Yanami Sub</span>
                <h3>{t.settings.acknowledgment.docs.title}</h3>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label={t.settings.acknowledgment.docs.close}
                onClick={() => setDocsOpen(false)}
              >
                <X size={18} />
              </button>
            </div>
            <p>{t.settings.acknowledgment.docs.intro}</p>
            <div className="docs-dialog-content">
              {t.settings.acknowledgment.docs.sections.map((section) => (
                <section key={section.title}>
                  <h4>{section.title}</h4>
                  <p>{section.body}</p>
                </section>
              ))}
            </div>
            <div className="dialog-actions">
              <button
                type="button"
                className="button button-primary"
                onClick={() => setDocsOpen(false)}
              >
                {t.settings.acknowledgment.docs.close}
              </button>
            </div>
          </article>
        </div>
      ) : null}
    </div>
  );
}
