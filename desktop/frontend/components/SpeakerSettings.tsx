"use client";

import type { TaskRequest } from "../lib/types";
import { CustomSelect } from "./CustomSelect";
import { useLanguage } from "./LanguageProvider";

export function SpeakerSettings({ request, disabled, onChange }: {
  request: Omit<TaskRequest, "input">; disabled?: boolean;
  onChange: (changes: Partial<Omit<TaskRequest, "input">>) => void;
}) {
  const { language } = useLanguage();
  const zh = language === "zh";
  const mode = request.diarize ?? "off";
  const joint = Boolean(request.asr && request.asr !== "local");
  const early = ["vocal", "aligned"].includes(request.stage);
  return <div className="field field-wide">
    <span>{zh ? "说话人分离（可选）" : "Speaker diarization (optional)"}</span>
    <CustomSelect value={mode} disabled={disabled || early}
      ariaLabel={zh ? "说话人分离" : "Speaker diarization"}
      onChange={(value) => onChange({ diarize: value as TaskRequest["diarize"], ...(value === "off" ? { speaker_tracks: "off" as const } : {}) })}
      options={[
        { value: "off", label: zh ? "关闭（默认）" : "Off (default)" },
        { value: "acoustics", label: zh ? "声学标签（不调用 LLM）" : "Acoustic labels (no LLM call)" },
        { value: "judge-text", label: zh ? "声学标签 + 文字裁判（实验）" : "Acoustics + text judge (experimental)" },
        { value: "judge-audio", label: zh ? "声学标签 + 音频裁判（实验）" : "Acoustics + audio judge (experimental)" },
      ]} />
    <small className="field-help">{zh ? "从字幕稳定化后执行；普通单轨 SRT 不变。轨号不是人物身份，可能需要人工合并或校对。" : "Runs after stabilization; the normal single-track SRT is unchanged. Track numbers are not identities and may need manual review."}</small>
    {joint ? <small className="field-help">{zh ? "一体转写自带说话人标签，不使用下方的声学模型；开启裁判会额外调用模型。" : "Joint transcription supplies speaker labels without an acoustic model. A judge adds model calls."}</small> : null}
    {mode !== "off" || joint ? <>
      {!joint ? <small className="field-help">{zh ? "默认模型首次按需下载约 450 MB，沿用任务设备；置信标主要按日语拟合，不保证中英文准确度。" : "The default model downloads about 450 MB on first use and follows the task device. Confidence marks were fitted mainly on Japanese, not validated for Chinese or English."}</small> : null}
      {mode.startsWith("judge-") ? <small className="field-help" role="note">{zh ? "裁判仍属实验，会在纠错阶段增加模型调用并可能消耗额度；仅输出原始字幕时只运行声学标签。音频裁判缺少生产实测。" : "The experimental judge adds model calls and may spend quota during correction. Raw-only tasks produce acoustic labels only. Audio judging lacks production acceptance."}</small> : null}
      <label className="field"><span>{zh ? "分轨导出" : "Speaker exports"}</span>
        <CustomSelect value={request.speaker_tracks ?? "off"} disabled={disabled || early}
          ariaLabel={zh ? "分轨导出" : "Speaker exports"}
          onChange={(value) => onChange({ speaker_tracks: value as TaskRequest["speaker_tracks"] })}
          options={[{ value: "off", label: zh ? "仅保留标签" : "Labels only" }, { value: "srt", label: zh ? "每轨一份 SRT" : "One SRT per track" },
            { value: "ass", label: zh ? "多轨 ASS" : "Multi-track ASS" }, { value: "both", label: "SRT + ASS" }]} />
      </label>
      {!joint ? <details><summary>{zh ? "高级：模型与人数限制" : "Advanced: model and speaker limit"}</summary>
        <div className="speaker-model-grid">
          <div className="field"><span>{zh ? "说话人模型" : "Diarization model"}</span>
            <CustomSelect value={request.diarize_backend ?? ""} disabled={disabled}
              ariaLabel={zh ? "说话人模型" : "Diarization model"}
              onChange={(value) => onChange({ diarize_backend: (value || null) as TaskRequest["diarize_backend"] })}
              options={[{ value: "", label: zh ? "核心默认（Nemotron-3，可商用）" : "Core default (Nemotron-3, commercial use allowed)" },
                { value: "nemotron3", label: "Nemotron-3" }, { value: "diarizen", label: zh ? "DiariZen（研究，仅非商业）" : "DiariZen (research, non-commercial only)" },
                { value: "sortformer", label: zh ? "Sortformer（研究，需自行导出）" : "Sortformer (research, user-exported model required)" }]} />
          </div>
          <label className="field"><span>{zh ? "人数上限（建议留空）" : "Speaker cap (leave blank recommended)"}</span>
            <input type="number" min={1} step={1} disabled={disabled} value={request.diarize_max_speakers ?? ""}
              onChange={(event) => onChange({ diarize_max_speakers: event.target.value ? Number(event.target.value) : null })} />
          </label>
        </div>
        <small className="field-help">{zh ? "限制人数可能把不同的人误合并。DiariZen 仅限非商业；Sortformer 需预先导出模型并设置 FINESUB_DIARIZATION_ARTIFACTS。已有时间线仍按核心规则复用，换模型不会自动覆盖。" : "A cap can wrongly merge different people. DiariZen is non-commercial; Sortformer requires an exported model and FINESUB_DIARIZATION_ARTIFACTS. Existing timelines are reused; changing the model does not overwrite them."}</small>
      </details> : null}
    </> : null}
  </div>;
}
