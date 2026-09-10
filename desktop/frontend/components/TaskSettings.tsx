"use client";

import { ChevronDown, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { invalidOutputName } from "@/lib/formatters";
import type {
  CapabilityState,
  GpuTier,
  RoutingSettings,
  TaskRequest,
} from "@/lib/types";

import { CustomSelect } from "./CustomSelect";
import { useLanguage } from "./LanguageProvider";


interface TaskSettingsProps {
  request: Omit<TaskRequest, "input">;
  capabilities: CapabilityState;
  routing?: RoutingSettings;
  disabled?: boolean;
  batchMode?: boolean;
  onChange: (changes: Partial<Omit<TaskRequest, "input">>) => void;
}


type SettingsTab = "speech" | "llm";


function optionalBooleanValue(value: boolean | null | undefined): string {
  if (value === true) return "on";
  if (value === false) return "off";
  return "";
}


function optionalBoolean(value: string): boolean | null {
  if (value === "on") return true;
  if (value === "off") return false;
  return null;
}


export function TaskSettings({
  request,
  capabilities,
  routing,
  disabled,
  batchMode = false,
  onChange,
}: TaskSettingsProps) {
  const { t } = useLanguage();
  const [tab, setTab] = useState<SettingsTab>("speech");
  const [advanced, setAdvanced] = useState(false);
  const [nameError, setNameError] = useState("");
  const translationSelected = ["translated-srt", "final-srt"].includes(
    request.stage,
  );
  // Surfaced on the tab itself: the note explaining the missing key lives
  // inside the LLM panel, which the user may not have open.
  const llmNeedsKey = translationSelected && !capabilities.translation;
  const stageLabels: Record<TaskRequest["stage"], string> = {
    vocal: t.processing.stages.vocal,
    aligned: t.processing.stages.aligned,
    stable: t.processing.stages.stable,
    "raw-srt": t.processing.stages.rawSrt,
    "translated-srt": t.processing.stages.translatedSrt,
    "final-srt": t.processing.stages.finalSrt,
  };
  const changeStage = (stage: TaskRequest["stage"]) =>
    onChange({ stage, ...(stage !== "raw-srt" ? { word: false } : {}) });
  const commonOutputOptions = [
    { value: "raw-srt", label: t.newTask.settings.outputRaw },
    { value: "final-srt", label: t.newTask.settings.outputFinal },
  ];
  if (request.stage !== "raw-srt" && request.stage !== "final-srt") {
    commonOutputOptions.push({
      value: request.stage,
      label: `${t.newTask.settings.expertCurrent}: ${stageLabels[request.stage]}`,
    });
  }

  return (
    <div className="task-settings">
      {/* Above the tabs, not inside either: this is the switch that decides
          whether the LLM tab means anything. */}
      <div className="field-grid">
        <div className="field">
          <span>{t.newTask.settings.output}</span>
          <CustomSelect
            value={request.stage}
            disabled={disabled}
            ariaLabel={t.newTask.settings.output}
            onChange={(value) => changeStage(value as TaskRequest["stage"])}
            options={commonOutputOptions}
          />
        </div>
      </div>

      <div className="task-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "speech"}
          className={`task-tab${tab === "speech" ? " is-active" : ""}`}
          onClick={() => setTab("speech")}
        >
          {t.newTask.settings.tabSpeech}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "llm"}
          className={`task-tab${tab === "llm" ? " is-active" : ""}`}
          onClick={() => setTab("llm")}
        >
          {t.newTask.settings.tabLlm}
          {llmNeedsKey ? <span className="tab-dot" aria-hidden="true" /> : null}
        </button>
      </div>

      {tab === "speech" ? (
        <div className="field-grid" role="tabpanel">
          <div className="field">
            <span>{t.newTask.settings.language}</span>
            <CustomSelect
              value={request.language ?? ""}
              disabled={disabled}
              ariaLabel={t.newTask.settings.language}
              onChange={(value) => onChange({ language: value || null })}
              options={[
                { value: "", label: t.newTask.settings.languageAuto },
                { value: "zh", label: t.newTask.settings.languageZh },
                { value: "ja", label: t.newTask.settings.languageJa },
                { value: "en", label: t.newTask.settings.languageEn },
                { value: "ko", label: t.newTask.settings.languageKo },
              ]}
            />
          </div>
          <div className="field">
            <span>{t.newTask.settings.gpuTier}</span>
            <CustomSelect
              value={request.gpu_tier}
              disabled={disabled}
              ariaLabel={t.newTask.settings.gpuTier}
              onChange={(value) => onChange({ gpu_tier: value as GpuTier })}
              options={[
                { value: "auto", label: t.newTask.settings.gpuTierAuto },
                { value: "cpu", label: t.newTask.settings.gpuTierCpu },
                { value: "entry", label: t.newTask.settings.gpuTierEntry },
                { value: "standard", label: t.newTask.settings.gpuTierStandard },
                {
                  value: "standard_large_vram",
                  label: t.newTask.settings.gpuTierStandardLargeVram,
                },
                { value: "high", label: t.newTask.settings.gpuTierHigh },
              ]}
            />
          </div>
        </div>
      ) : (
        <div className="tab-panel" role="tabpanel">
          {!translationSelected ? (
            <div className="inline-note tab-note">
              <span>{t.newTask.settings.llmInactive}</span>
              <button
                type="button"
                className="button button-secondary button-compact"
                disabled={disabled}
                onClick={() => onChange({ stage: "final-srt" })}
              >
                {t.newTask.settings.llmEnable}
              </button>
            </div>
          ) : null}
          {llmNeedsKey ? (
            <div className="inline-note">{t.newTask.apiKeyError}</div>
          ) : null}
          {/* Values are kept, not cleared, while the stage leaves them unused:
              switching back to final-srt must find them where they were. */}
          <div className="field-grid">
            <label className="field field-wide">
              <span>{t.newTask.settings.extraInfo}</span>
              <textarea
                value={request.extra_info}
                disabled={disabled || !translationSelected}
                rows={3}
                placeholder={t.newTask.settings.extraInfoPlaceholder}
                onChange={(event) =>
                  onChange({ extra_info: event.target.value })
                }
              />
            </label>
            <div className="field">
              <span>{t.newTask.settings.knowledge}</span>
              <CustomSelect
                value={request.knowledge}
                disabled={disabled || !translationSelected}
                ariaLabel={t.newTask.settings.knowledge}
                onChange={(value) =>
                  onChange({ knowledge: value as TaskRequest["knowledge"] })
                }
                options={[
                  { value: "update", label: t.newTask.settings.knowledgeUpdate },
                  { value: "collect", label: t.newTask.settings.knowledgeCollect },
                  { value: "none", label: t.newTask.settings.knowledgeNone },
                ]}
              />
            </div>
          </div>
        </div>
      )}

      {/* Both apply to every run, not just an unusual one, so they sit in the
          open: the naming choice has to be made before the task starts, and
          the cleanup switch decides what survives it. */}
      <div className="advanced-grid">
        {!batchMode ? (
          <label className="field">
            <span>{t.newTask.settings.outputName}</span>
            <input
              value={request.name}
              disabled={disabled}
              onChange={(event) => {
                const value = event.target.value;
                // Explained only when it is wrong: the rule is narrow enough
                // that a permanent hint is noise on every other keystroke.
                setNameError(
                  invalidOutputName(value) ? t.newTask.settings.outputNameError : "",
                );
                onChange({ name: value });
              }}
            />
            {nameError ? <small className="field-error">{nameError}</small> : null}
          </label>
        ) : null}
        <label className="switch-row">
          <input
            type="checkbox"
            checked={request.cleanup_intermediate}
            disabled={disabled}
            onChange={(event) =>
              onChange({ cleanup_intermediate: event.target.checked })
            }
          />
          <span>
            <strong>{t.newTask.settings.cleanup}</strong>
            <small>{t.newTask.settings.cleanupHint}</small>
          </span>
        </label>
      </div>

      <button
        type="button"
        className="advanced-toggle"
        aria-expanded={advanced}
        onClick={() => setAdvanced((value) => !value)}
      >
        <SlidersHorizontal size={14} />
        {t.newTask.settings.advanced}
        <ChevronDown
          size={14}
          className={advanced ? "is-rotated" : ""}
          aria-hidden="true"
        />
      </button>

      {advanced ? (
        <div className="advanced-grid advanced-grid-animated">
          {tab === "speech" ? (
            <>
              <div className="advanced-section-heading">
                <strong>{t.newTask.settings.advancedSpeech}</strong>
                <small>{t.newTask.settings.advancedSpeechHint}</small>
              </div>
              <div className="field">
                <span>{t.newTask.settings.expertStage}</span>
                <CustomSelect
                  value={request.stage}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.expertStage}
                  onChange={(value) => changeStage(value as TaskRequest["stage"])}
                  options={Object.entries(stageLabels).map(([value, label]) => ({
                    value,
                    label,
                  }))}
                />
              </div>
              <label className="field">
                <span>{t.newTask.settings.modelName}</span>
                <input
                  value={request.model_name}
                  disabled={disabled}
                  onChange={(event) => onChange({ model_name: event.target.value })}
                />
              </label>
              <div className="field">
                <span>{t.newTask.settings.separation}</span>
                <CustomSelect
                  value={optionalBooleanValue(request.separate)}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.separation}
                  onChange={(value) => onChange({ separate: optionalBoolean(value) })}
                  options={[
                    { value: "", label: t.newTask.settings.followCore },
                    { value: "on", label: t.newTask.settings.enabled },
                    { value: "off", label: t.newTask.settings.cleanVocal },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.separatorSampleRate}</span>
                <CustomSelect
                  value={request.separator_sample_rate?.toString() ?? ""}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.separatorSampleRate}
                  onChange={(value) =>
                    onChange({
                      separator_sample_rate: value
                        ? (Number(value) as 44100 | 32000 | 22050)
                        : null,
                    })
                  }
                  options={[
                    { value: "", label: t.newTask.settings.followCore },
                    { value: "44100", label: "44,100 Hz" },
                    { value: "32000", label: "32,000 Hz" },
                    { value: "22050", label: "22,050 Hz" },
                  ]}
                />
              </div>
              <label className="field">
                <span>{t.newTask.settings.gapSeconds}</span>
                <input
                  type="number"
                  min="0"
                  step="0.05"
                  value={request.gap_sec}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({ gap_sec: Math.max(0, Number(event.target.value)) })
                  }
                />
              </label>
              <div className="field">
                <span>{t.newTask.settings.stabilizeProfile}</span>
                <CustomSelect
                  value={request.asr_stabilize_profile.toString()}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.stabilizeProfile}
                  onChange={(value) =>
                    onChange({
                      asr_stabilize_profile: Number(value) as -1 | 0 | 1 | 2,
                    })
                  }
                  options={[
                    { value: "-1", label: t.newTask.settings.profileNoop },
                    { value: "0", label: t.newTask.settings.profileDefault },
                    { value: "1", label: t.newTask.settings.profileCleanup },
                    { value: "2", label: t.newTask.settings.profileNoisy },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.vadAssist}</span>
                <CustomSelect
                  value={optionalBooleanValue(request.vad_silero_assist)}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.vadAssist}
                  onChange={(value) =>
                    onChange({ vad_silero_assist: optionalBoolean(value) })
                  }
                  options={[
                    { value: "", label: t.newTask.settings.followCore },
                    { value: "on", label: t.newTask.settings.enabled },
                    { value: "off", label: t.newTask.settings.disabled },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.qwenVerify}</span>
                <CustomSelect
                  value={request.qwen_verify}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.qwenVerify}
                  onChange={(value) =>
                    onChange({ qwen_verify: value as TaskRequest["qwen_verify"] })
                  }
                  options={[
                    { value: "auto", label: t.newTask.settings.automatic },
                    { value: "on", label: t.newTask.settings.enabled },
                    { value: "off", label: t.newTask.settings.disabled },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.langRedecode}</span>
                <CustomSelect
                  value={request.lang_redecode}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.langRedecode}
                  onChange={(value) =>
                    onChange({ lang_redecode: value as TaskRequest["lang_redecode"] })
                  }
                  options={[
                    { value: "auto", label: t.newTask.settings.automatic },
                    { value: "on", label: t.newTask.settings.enabled },
                    { value: "off", label: t.newTask.settings.disabled },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.asrContext}</span>
                <CustomSelect
                  value={request.asr_context}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.asrContext}
                  onChange={(value) =>
                    onChange({ asr_context: value as TaskRequest["asr_context"] })
                  }
                  options={[
                    { value: "off", label: t.newTask.settings.contextOff },
                    { value: "terms", label: t.newTask.settings.contextTerms },
                    { value: "full", label: t.newTask.settings.contextFull },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.decodeBatch}</span>
                <CustomSelect
                  value={request.asr_decode_batch.toString()}
                  disabled={disabled}
                  ariaLabel={t.newTask.settings.decodeBatch}
                  onChange={(value) =>
                    onChange({
                      asr_decode_batch: value === "auto" ? "auto" : Number(value),
                    })
                  }
                  options={[
                    { value: "auto", label: t.newTask.settings.automatic },
                    { value: "1", label: "1" },
                    { value: "2", label: "2" },
                    { value: "4", label: "4" },
                    { value: "8", label: "8" },
                    { value: "16", label: "16" },
                  ]}
                />
              </div>
              <label className="field">
                <span>{t.newTask.settings.lengthScaleOverride}</span>
                <input
                  type="number"
                  min="0.6"
                  max="1.6"
                  step="0.05"
                  value={request.split_length_scale ?? ""}
                  placeholder={t.newTask.settings.followSharedSetting}
                  disabled={disabled}
                  onChange={(event) =>
                    onChange({
                      split_length_scale: event.target.value
                        ? Number(event.target.value)
                        : null,
                    })
                  }
                />
              </label>
              <label className="switch-row switch-row-compact">
                <input
                  type="checkbox"
                  checked={request.word}
                  disabled={disabled || request.stage !== "raw-srt"}
                  onChange={(event) => onChange({ word: event.target.checked })}
                />
                <span>
                  <strong>{t.newTask.settings.wordTimestamps}</strong>
                  <small>{t.newTask.settings.wordTimestampsHint}</small>
                </span>
              </label>
            </>
          ) : (
            <>
              <div className="advanced-section-heading">
                <strong>{t.newTask.settings.advancedLlm}</strong>
                <small>{t.newTask.settings.advancedLlmHint}</small>
              </div>
              <label className="field field-wide">
                <span>{t.newTask.settings.modelOverrides}</span>
                <textarea
                  rows={3}
                  value={request.llm_model.join("\n")}
                  disabled={disabled || !translationSelected}
                  placeholder={t.newTask.settings.modelOverridesPlaceholder}
                  onChange={(event) =>
                    onChange({ llm_model: event.target.value.split(/\r?\n/) })
                  }
                />
                <small
                  className="field-help"
                  title={[
                    ...Object.keys(routing?.model_groups ?? {}),
                    ...(routing?.targets ?? []).map((target) => target.id),
                  ].join(", ")}
                >
                  {t.newTask.settings.modelOverridesHint.replace(
                    "{count}",
                    String(
                      Object.keys(routing?.model_groups ?? {}).length +
                        (routing?.targets.length ?? 0),
                    ),
                  )}
                </small>
              </label>
              <div className="field">
                <span>{t.newTask.settings.llmMedia}</span>
                <CustomSelect
                  value={request.llm_media}
                  disabled={disabled || !translationSelected}
                  ariaLabel={t.newTask.settings.llmMedia}
                  onChange={(value) =>
                    onChange({ llm_media: value as TaskRequest["llm_media"] })
                  }
                  options={[
                    { value: "text", label: t.newTask.settings.mediaText },
                    { value: "audio", label: t.newTask.settings.mediaAudio },
                    { value: "video", label: t.newTask.settings.mediaVideo },
                  ]}
                />
              </div>
              {(["correction", "planning"] as const).map((kind) => {
                const key = kind === "correction" ? "llm_correction_media" : "llm_planning_media";
                const label = kind === "correction"
                  ? t.newTask.settings.correctionMedia
                  : t.newTask.settings.planningMedia;
                return (
                  <div className="field" key={kind}>
                    <span>{label}</span>
                    <CustomSelect
                      value={request[key]}
                      disabled={disabled || !translationSelected}
                      ariaLabel={label}
                      onChange={(value) => onChange({ [key]: value })}
                      options={[
                        { value: "", label: t.newTask.settings.inheritMedia },
                        { value: "text", label: t.newTask.settings.mediaText },
                        { value: "audio", label: t.newTask.settings.mediaAudio },
                        { value: "video", label: t.newTask.settings.mediaVideo },
                      ]}
                    />
                  </div>
                );
              })}
              <div className="field">
                <span>{t.newTask.settings.retrieval}</span>
                <CustomSelect
                  value={request.llm_retrieval}
                  disabled={disabled || !translationSelected}
                  ariaLabel={t.newTask.settings.retrieval}
                  onChange={(value) =>
                    onChange({ llm_retrieval: value as TaskRequest["llm_retrieval"] })
                  }
                  options={[
                    { value: "none", label: t.newTask.settings.retrievalNone },
                    { value: "local", label: t.newTask.settings.retrievalLocal },
                    { value: "native", label: t.newTask.settings.retrievalNative },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.difficulty}</span>
                <CustomSelect
                  value={request.llm_difficulty}
                  disabled={disabled || !translationSelected}
                  ariaLabel={t.newTask.settings.difficulty}
                  onChange={(value) =>
                    onChange({ llm_difficulty: value as TaskRequest["llm_difficulty"] })
                  }
                  options={[
                    { value: "quality", label: t.newTask.settings.quality },
                    { value: "intermediate", label: t.newTask.settings.intermediate },
                    { value: "efficiency", label: t.newTask.settings.efficiency },
                  ]}
                />
              </div>
              <div className="field">
                <span>{t.newTask.settings.continuity}</span>
                <CustomSelect
                  value={request.llm_continuity}
                  disabled={disabled || !translationSelected}
                  ariaLabel={t.newTask.settings.continuity}
                  onChange={(value) =>
                    onChange({ llm_continuity: value as TaskRequest["llm_continuity"] })
                  }
                  options={[
                    { value: "serial", label: t.newTask.settings.continuitySerial },
                    { value: "parallel", label: t.newTask.settings.continuityParallel },
                  ]}
                />
              </div>
              <label className="field">
                <span>{t.newTask.settings.parallelWindows}</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={request.llm_parallel_windows}
                  disabled={disabled || !translationSelected}
                  onChange={(event) =>
                    onChange({ llm_parallel_windows: Math.max(1, Number(event.target.value)) })
                  }
                />
              </label>
              <div className="field">
                <span>{t.newTask.settings.fastMode}</span>
                <CustomSelect
                  value={request.llm_fast}
                  disabled={disabled || !translationSelected}
                  ariaLabel={t.newTask.settings.fastMode}
                  onChange={(value) =>
                    onChange({ llm_fast: value as TaskRequest["llm_fast"] })
                  }
                  options={[
                    { value: "auto", label: t.newTask.settings.automatic },
                    { value: "on", label: t.newTask.settings.enabled },
                    { value: "off", label: t.newTask.settings.disabled },
                  ]}
                />
              </div>
              <label className="field">
                <span>{t.newTask.settings.outputScale}</span>
                <input
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={request.llm_output_scale}
                  disabled={disabled || !translationSelected}
                  onChange={(event) =>
                    onChange({ llm_output_scale: Math.max(0.1, Number(event.target.value)) })
                  }
                />
              </label>
              <div className="field">
                <span>{t.newTask.settings.postprocessProfile}</span>
                <CustomSelect
                  value={request.postprocess_profile.toString()}
                  disabled={disabled || !translationSelected}
                  ariaLabel={t.newTask.settings.postprocessProfile}
                  onChange={(value) =>
                    onChange({
                      postprocess_profile: Number(value) as -1 | 0 | 1 | 2 | 3 | 4,
                    })
                  }
                  options={[
                    { value: "-1", label: t.newTask.settings.postprocessNone },
                    { value: "0", label: t.newTask.settings.postprocessAll },
                    { value: "1", label: t.newTask.settings.postprocessDuration },
                    { value: "2", label: t.newTask.settings.postprocessPunctuation },
                    { value: "3", label: t.newTask.settings.postprocessT2s },
                    { value: "4", label: t.newTask.settings.postprocessOverlap },
                  ]}
                />
              </div>
              <label className="field field-wide">
                <span>{t.newTask.settings.extraStyle}</span>
                <textarea
                  rows={3}
                  value={request.extra_style}
                  disabled={disabled || !translationSelected}
                  placeholder={t.newTask.settings.extraStylePlaceholder}
                  onChange={(event) => onChange({ extra_style: event.target.value })}
                />
              </label>
              <label className="field field-wide">
                <span>{t.newTask.settings.taskSummary}</span>
                <textarea
                  rows={2}
                  value={request.task_summary ?? ""}
                  disabled={disabled || !translationSelected}
                  placeholder={t.newTask.settings.taskSummaryPlaceholder}
                  onChange={(event) => onChange({ task_summary: event.target.value })}
                />
              </label>
              <label className="field">
                <span>{t.newTask.settings.namedStyle}</span>
                <input
                  value={request.style ?? ""}
                  disabled={disabled || !translationSelected}
                  placeholder={t.newTask.settings.namedStylePlaceholder}
                  onChange={(event) => onChange({ style: event.target.value || null })}
                />
              </label>
              <div className="field">
                <span>{t.newTask.settings.styleMode}</span>
                <CustomSelect
                  value={request.style_mode ?? ""}
                  disabled={disabled || !translationSelected}
                  ariaLabel={t.newTask.settings.styleMode}
                  onChange={(value) =>
                    onChange({
                      style_mode: (value || null) as TaskRequest["style_mode"],
                    })
                  }
                  options={[
                    { value: "", label: t.newTask.settings.followCore },
                    { value: "none", label: t.newTask.settings.styleNone },
                    { value: "read", label: t.newTask.settings.styleRead },
                    { value: "update", label: t.newTask.settings.styleUpdate },
                  ]}
                />
              </div>
              <label className="field">
                <span>{t.newTask.settings.llmVideo}</span>
                <input
                  value={request.llm_video ?? ""}
                  disabled={disabled || !translationSelected}
                  placeholder={t.newTask.settings.optionalPath}
                  onChange={(event) => onChange({ llm_video: event.target.value || null })}
                />
              </label>
              <label className="field field-wide">
                <span>{t.newTask.settings.refinedSrt}</span>
                <input
                  value={request.refined_srt ?? ""}
                  disabled={disabled || !translationSelected}
                  placeholder={t.newTask.settings.refinedSrtPlaceholder}
                  onChange={(event) => onChange({ refined_srt: event.target.value || null })}
                />
              </label>
              <label className="field">
                <span>{t.newTask.settings.maxRetries}</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={request.max_retries_per_window}
                  disabled={disabled || !translationSelected}
                  onChange={(event) =>
                    onChange({ max_retries_per_window: Math.max(0, Number(event.target.value)) })
                  }
                />
              </label>
              <label className="field">
                <span>{t.newTask.settings.maxReplacements}</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={request.max_replacements_per_window}
                  disabled={disabled || !translationSelected}
                  onChange={(event) =>
                    onChange({
                      max_replacements_per_window: Math.max(0, Number(event.target.value)),
                    })
                  }
                />
              </label>
              <label className="switch-row switch-row-compact">
                <input
                  type="checkbox"
                  checked={request.download_video_source}
                  disabled={disabled || !translationSelected}
                  onChange={(event) =>
                    onChange({ download_video_source: event.target.checked })
                  }
                />
                <span>
                  <strong>{t.newTask.settings.downloadVideo}</strong>
                  <small>{t.newTask.settings.downloadVideoHint}</small>
                </span>
              </label>
              <label className="switch-row switch-row-compact">
                <input
                  type="checkbox"
                  checked={request.resume}
                  disabled={disabled || !translationSelected}
                  onChange={(event) => onChange({ resume: event.target.checked })}
                />
                <span>
                  <strong>{t.newTask.settings.resume}</strong>
                  <small>{t.newTask.settings.resumeHint}</small>
                </span>
              </label>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
