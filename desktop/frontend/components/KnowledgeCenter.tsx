"use client";

import {
  BookOpenText,
  Download,
  FilePenLine,
  FolderOpen,
  Plus,
  RefreshCw,
  Save,
  Search,
  Share2,
  ShieldCheck,
  Upload,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { BridgeCallError, desktopApi } from "@/lib/bridge";
import { runInterfaceTransition } from "@/lib/viewTransition";
import { saveUi, uiValue } from "@/lib/preferences";
import type {
  JobSnapshot,
  KnowledgeEntryDocument,
  KnowledgeFeedback,
  KnowledgeMaintenanceCommand,
  KnowledgeShareCommand,
  KnowledgeSnapshot,
  TaskRequest,
  RefinedKnowledgeUpdateReport,
  RoutingSettings,
} from "@/lib/types";

import { useLanguage } from "./LanguageProvider";
import { useToast } from "./ToastProvider";
import { ConfirmDialog } from "./ConfirmDialog";
import { KnowledgeStructure } from "./KnowledgeStructure";
import { KnowledgeDocument } from "./KnowledgeDocument";
import { KnowledgeRecovery } from "./KnowledgeRecovery";
import { KnowledgeFileExchange } from "./KnowledgeFileExchange";
import { CustomSelect } from "./CustomSelect";
import { BilingualKnowledgeImport, ProposalReview, canApplyProposal, knowledgeOutcome } from "./BilingualKnowledgeImport";


type KnowledgeTab = "library" | "feedback" | "maintenance" | "sharing";

interface KnowledgeCenterProps {
  tasks: JobSnapshot[];
  routing?: RoutingSettings;
}

type CompletedKnowledgeTask = JobSnapshot & {
  task_id: string;
  request: TaskRequest & { output: string };
};

const ENTRY_TYPES = ["游戏", "动画", "社区", "其他"] as const;


function errorMessage(error: unknown): string {
  if (error instanceof BridgeCallError || error instanceof Error) {
    return error.message;
  }
  return String(error);
}


function isCompletedKnowledgeTask(task: JobSnapshot): task is CompletedKnowledgeTask {
  return (
    task.state === "completed" &&
    typeof task.task_id === "string" &&
    typeof task.request?.output === "string" &&
    task.request.output.length > 0
  );
}


function taskLabel(task: CompletedKnowledgeTask): string {
  const source = task.request.input.split(/[\\/]/).pop() || task.request.input;
  return `${source} · ${task.task_id}`;
}


export function KnowledgeCenter({ tasks, routing }: KnowledgeCenterProps) {
  const { t, language } = useLanguage();
  const { showSuccess } = useToast();
  const [tab, setTab] = useState<KnowledgeTab>(() => uiValue("rememberLastSettings", true) ? uiValue<KnowledgeTab>("knowledgeTab", "library") : "library");
  const [snapshot, setSnapshot] = useState<KnowledgeSnapshot | null>(null);
  const [document, setDocument] = useState<KnowledgeEntryDocument | null>(null);
  const [draft, setDraft] = useState("");
  const [selectedName, setSelectedName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState(() => uiValue("rememberLastSettings", true) ? uiValue("knowledgeCategory", "all") : "all");
  useEffect(() => { if (uiValue("rememberLastSettings", true)) saveUi({ knowledgeTab: tab, knowledgeCategory: category }); }, [tab, category]);
  const selectTab = (next: KnowledgeTab) => {
    if (next === tab || busy) return;
    setError(""); setOutput("");
    runInterfaceTransition(() => setTab(next));
  };

  const [newEntry, setNewEntry] = useState({
    category: "common",
    key: "",
    intro: "",
    entryType: "其他",
    aliases: "",
  });
  const [showCreate, setShowCreate] = useState(false);

  const completedTasks = useMemo(
    () => tasks.filter(isCompletedKnowledgeTask),
    [tasks],
  );
  const [feedbackTaskId, setFeedbackTaskId] = useState("");
  const [feedback, setFeedback] = useState<KnowledgeFeedback | null>(null);
  const [refinedPath, setRefinedPath] = useState("");
  const [sourcePath, setSourcePath] = useState("");
  const [refinedError, setRefinedError] = useState("");
  const [feedbackError, setFeedbackError] = useState("");
  const [refinedProposal, setRefinedProposal] = useState<RefinedKnowledgeUpdateReport | null>(null);
  const [confirmation, setConfirmation] = useState<{ message: string; action: () => void } | null>(null);
  const confirmAction = (message: string, action: () => void) => setConfirmation({ message, action });

  useEffect(() => { setRefinedProposal(null); setRefinedError(""); }, [refinedPath, sourcePath, feedbackTaskId]);
  useEffect(() => { setSourcePath(""); setFeedback(null); setFeedbackError(""); }, [feedbackTaskId]);

  const [candidateReason, setCandidateReason] = useState("");
  const [restoreId, setRestoreId] = useState("");
  const [ingest, setIngest] = useState({ subject: "", material: "", prompt: "" });

  const [remote, setRemote] = useState("");
  const remoteArgs = remote.trim() ? ["--remote", remote.trim()] : [];
  const [shareKinds, setShareKinds] = useState("");
  const [shareMatch, setShareMatch] = useState("");
  const [queueId, setQueueId] = useState("");
  const [conflictReason, setConflictReason] = useState("");
  const [maintainer, setMaintainer] = useState({ token: "", queueId: "", override: "" });

  const loadSnapshot = async (keepSelection = true) => {
    setError("");
    const next = await desktopApi.getKnowledgeSnapshot();
    setSnapshot(next);
    if (!feedbackTaskId && completedTasks.length) setFeedbackTaskId(completedTasks[0].task_id);
    if (!keepSelection || !next.entries.some((entry) => entry.qualified_name === selectedName)) {
      setSelectedName(next.entries[0]?.qualified_name || "");
      setDocument(null);
      setDraft("");
    }
    return next;
  };

  useEffect(() => {
    let active = true;
    void desktopApi.getKnowledgeSnapshot()
      .then((next) => {
        if (!active) return;
        setSnapshot(next);
        setSelectedName(next.entries[0]?.qualified_name || "");
        setRemote(next.registered_remotes[0] || "");
        setFeedbackTaskId(completedTasks[0]?.task_id || "");
      })
      .catch((reason) => active && setError(errorMessage(reason)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedName) {
      setDocument(null);
      setDraft("");
      return;
    }
    let active = true;
    void desktopApi.getKnowledgeEntry(selectedName)
      .then((next) => {
        if (!active) return;
        setDocument(next);
        setDraft(next.text);
      })
      .catch((reason) => active && setError(errorMessage(reason)));
    return () => {
      active = false;
    };
  }, [selectedName]);

  const visibleEntries = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return (snapshot?.entries || []).filter((entry) => {
      if (category !== "all" && entry.category !== category) return false;
      if (!needle) return true;
      return [entry.key, entry.qualified_name, entry.intro, ...entry.aliases]
        .join(" ")
        .toLocaleLowerCase()
        .includes(needle);
    });
  }, [snapshot, search, category]);

  const runMaintenance = async (
    command: KnowledgeMaintenanceCommand,
    args: string[] = [],
    content = "",
  ) => {
    setBusy(true);
    setError("");
    try {
      const result = await desktopApi.runKnowledgeMaintenance({ command, args, content });
      setOutput(result.output || `${command}: OK`);
      await loadSnapshot();
      if (selectedName && command === "edit") {
        const next = await desktopApi.getKnowledgeEntry(selectedName);
        setDocument(next);
        setDraft(next.text);
      }
      showSuccess(language === "zh" ? "操作完成，写入结果请查看报告" : "Operation finished; review the report for write results", `knowledge-maintenance-${command}`);
      return result;
    } catch (reason) {
      setError(errorMessage(reason));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const runShare = async (command: KnowledgeShareCommand, args: string[] = []) => {
    setBusy(true);
    setError("");
    try {
      const result = await desktopApi.runKnowledgeShare({ command, args });
      setOutput(result.output || `share ${command}: OK`);
      await loadSnapshot();
      showSuccess(language === "zh" ? "共享操作已完成，请查看报告" : "Sharing operation finished; review the report", `knowledge-share-${command}`);
      return result;
    } catch (reason) {
      const raw = errorMessage(reason);
      const hint = /not registered/i.test(raw)
        ? (language === "zh" ? "请先点击“首次投稿：注册”，再提交。" : "Register once before submitting.")
        : /no .*shareable|no .*marked|nothing to push/i.test(raw)
          ? (language === "zh" ? "请先选择条目并“标记可共享”。" : "Choose an entry and mark it shareable first.")
          : ["register", "pull", "push", "status"].includes(command)
            ? (language === "zh" ? "请检查地址与网络；默认社区不可用时可稍后重试，或先用本地文件交换。请勿为重试而清空知识库。" : "Check the address and connection. If the community is unavailable, retry later or exchange a local file. Do not clear your library to retry.") : "";
      setError(hint ? `${hint}\n${raw}` : raw);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const createEntry = async () => {
    const args = [newEntry.category, newEntry.key.trim(), "--intro", newEntry.intro.trim()];
    if (newEntry.category === "common") args.push("--type", newEntry.entryType);
    for (const alias of newEntry.aliases.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean)) {
      args.push("--alias", alias);
    }
    const result = await runMaintenance("new", args);
    if (result) {
      const qualified = `${newEntry.category}/${newEntry.key.trim()}`;
      setSelectedName(qualified);
      setNewEntry({ category: "common", key: "", intro: "", entryType: "其他", aliases: "" });
      setShowCreate(false);
    }
  };

  const selectedTask = completedTasks.find((task) => task.task_id === feedbackTaskId);

  const loadFeedback = async () => {
    if (!feedbackTaskId) return;
    setBusy(true);
    setFeedbackError("");
    try {
      setFeedback(await desktopApi.getTaskKnowledgeFeedback(feedbackTaskId));
    } catch (reason) {
      setFeedbackError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  const chooseFile = async (target: "refined" | "source" | "material") => {
    try {
      const chosen = await desktopApi.selectSubtitleFile();
      if (!chosen.path) return;
      if (target === "refined") setRefinedPath(chosen.path);
      else if (target === "source") setSourcePath(chosen.path);
      else setIngest((current) => ({ ...current, material: chosen.path || "" }));
    } catch (reason) {
      if (target === "material") setError(errorMessage(reason));
      else setRefinedError(errorMessage(reason));
    }
  };

  const applyRefined = async (apply: boolean) => {
    if (!selectedTask || !refinedPath.trim()) return;
    if (apply && !refinedProposal?.draft_id) return;
    if (!apply) setRefinedProposal(null);
    setBusy(true);
    setRefinedError("");
    try {
      const report = apply && refinedProposal?.draft_id ? await desktopApi.applyKnowledgeProposal(refinedProposal.draft_id) : await desktopApi.runRefinedKnowledgeUpdate({
        task_id: selectedTask.task_id,
        refined_srt: refinedPath.trim(),
        source_srt: sourcePath.trim(),
        task_summary: selectedTask.request.task_summary,
        llm_model: selectedTask.request.llm_model,
        apply: false,
        resume: true,
      });
      setRefinedProposal(report);
      setOutput(JSON.stringify(report, null, 2));
      await loadSnapshot();
      if (report.status === "applied" || report.status === "generated" || report.status === "evidence_only") showSuccess(knowledgeOutcome(report, language === "zh"), "knowledge-refined-update");
    } catch (reason) {
      setRefinedError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  const tabs: Array<{ id: KnowledgeTab; label: string; icon: typeof BookOpenText }> = [
    { id: "library", label: t.knowledge.tabs.library, icon: BookOpenText },
    { id: "feedback", label: t.knowledge.tabs.feedback, icon: FilePenLine },
    { id: "maintenance", label: t.knowledge.tabs.maintenance, icon: Wrench },
    { id: "sharing", label: t.knowledge.tabs.sharing, icon: Share2 },
  ];

  return (
    <div className="page page-knowledge">
      <header className="page-header knowledge-header">
        <div>
          <h1>{t.knowledge.title}</h1>
          <p>{t.knowledge.description}</p>
        </div>
        <div className="knowledge-header-actions">
          {loading ? (
            <span className="knowledge-revision">{t.knowledge.loading}</span>
          ) : snapshot ? (
            <span className="knowledge-revision">{`rev ${snapshot.revision}`}</span>
          ) : null}
          <button type="button" className="button button-secondary" disabled={busy} onClick={() => void loadSnapshot()}>
            <RefreshCw size={15} />
            {t.knowledge.refresh}
          </button>
          <button type="button" className="button button-secondary" onClick={() => void desktopApi.openKnowledgeDirectory()}>
            <FolderOpen size={15} />
            {t.knowledge.openFolder}
          </button>
        </div>
      </header>

      <div className="knowledge-tabs" role="tablist" aria-label={t.knowledge.tabs.aria}>
        {tabs.map((item) => {
          const Icon = item.icon;
          return (
            <button
              type="button"
              key={item.id}
              className={tab === item.id ? "is-active" : ""}
              role="tab"
              aria-selected={tab === item.id}
              disabled={busy}
              onClick={() => selectTab(item.id)}
            >
              <Icon size={15} />
              {item.label}
            </button>
          );
        })}
      </div>

      <aside className="knowledge-guide" aria-label={language === "zh" ? "操作指南" : "Workflow guide"}>
        <strong>{language === "zh" ? ({ library: "管理会反复用到的术语、译名和字幕风格", feedback: "把人工修订的字幕变成可复用知识", maintenance: "排查知识库问题，或找回之前的内容", sharing: "与社区交换知识；不影响本地独立使用" }[tab]) : ({ library: "Manage reusable terms, names and subtitle styles", feedback: "Learn reusable knowledge from refined subtitles", maintenance: "Check the store or restore earlier content", sharing: "Exchange knowledge with a community server" }[tab])}</strong>
        <p>{language === "zh" ? ({ library: "先选择左侧条目阅读；需要修改时展开“编辑原文”并保存。停用可在“检查与恢复”中撤销。新建任务的“知识库”选项决定是否读取或更新这些内容。", feedback: "只有两份时间轴一致的字幕？使用“双语字幕导入”，不需要原任务。若有本应用的原任务，可选择任务并导入精修字幕。两种方式都先生成提案，审阅后再写入。生成会调用所选模型，应用同一提案不再次调用模型。", maintenance: "重建缓存和确定性迁移不调用模型。其他工具的“查看计划”只展示工作范围；“生成建议”调用模型但不写入，“生成并写入”会调用模型并更新知识库。它们不是应用同一份预览提案。", sharing: "发给朋友：用下方“本地文件交换”，无需服务器。获取或贡献社区知识：用“联网社区”，默认地址已内置。共享为可选功能，发出前请核对正文隐私。" }[tab]) : ({ library: "Choose an entry to read it. Expand Edit source to make changes, then save. Retired entries can be restored under Check & restore. Each task controls whether this knowledge is read or updated.", feedback: "Two matching subtitle files need no original task: use bilingual import. For an existing app task, import a refined SRT below. Generate a proposal first, review it, then apply that exact proposal without another model call.", maintenance: "Cache rebuilding and deterministic migration make no model calls. View plan shows scope only; Generate suggestions calls models without writing; Generate & write calls models and changes the store. These are separate runs, not application of the same preview proposal.", sharing: "Send to a friend with Local file exchange; no server is needed. Receive or contribute knowledge with Online community; its default address is built in. Sharing is optional. Review text for private content before sending." }[tab])}</p>
      </aside>

      {error ? <div className="inline-error knowledge-error" role="alert">{error}</div> : null}
      {loading ? <div className="primary-panel knowledge-loading">{t.knowledge.loading}</div> : null}

      {!loading && tab === "library" ? (
        <div className="knowledge-library">
          <aside className="primary-panel knowledge-browser">
            <div className="knowledge-browser-tools">
              <label className="knowledge-search">
                <Search size={15} />
                <input value={search} placeholder={t.knowledge.search} onChange={(event) => setSearch(event.target.value)} />
              </label>
              <CustomSelect value={category} onChange={setCategory} ariaLabel={t.knowledge.category}
                options={["all", "streamer", "common", "style"].map((value) => ({ value, label: t.knowledge.categories[value as keyof typeof t.knowledge.categories] }))} />
            </div>
            <div className="knowledge-entry-count">
              {t.knowledge.entryCount.replace("{count}", String(visibleEntries.length))}
            </div>
            <div className="knowledge-entry-list">
              {visibleEntries.map((entry) => (
                <button
                  type="button"
                  key={entry.id}
                  className={selectedName === entry.qualified_name ? "is-active" : ""}
                  disabled={busy}
                  onClick={() => {
                    if (selectedName === entry.qualified_name) { setShowCreate(false); return; }
                    const select = () => { setSelectedName(entry.qualified_name); setShowCreate(false); };
                    if (document && draft !== document.text) confirmAction(language === "zh" ? "当前条目有未保存的修改，切换后将丢弃这些修改。继续切换？" : "This entry has unsaved changes. Switching discards them. Continue?", select);
                    else select();
                  }}
                >
                  <span>
                    <strong>{entry.key}</strong>
                    <small>{t.knowledge.categories[entry.category as "streamer" | "common" | "style"] || entry.category}</small>
                  </span>
                  <span className={`knowledge-visibility is-${entry.visibility}`}>
                    {entry.visibility === "shareable" ? t.knowledge.shareable : t.knowledge.local}
                  </span>
                </button>
              ))}
              {!visibleEntries.length ? <p className="empty-copy">{t.knowledge.empty}</p> : null}
            </div>
            <button type="button" className="button button-secondary knowledge-create-toggle" onClick={() => setShowCreate((value) => !value)}>
              <Plus size={15} />
              {t.knowledge.create.title}
            </button>
          </aside>

          <section className="primary-panel knowledge-editor">
            {showCreate ? (
              <div className="knowledge-create-form">
                <div className="section-heading">
                  <div>
                    <h2>{t.knowledge.create.title}</h2>
                    <p>{t.knowledge.create.hint}</p>
                  </div>
                </div>
                <div className="knowledge-form-grid">
                  <div className="field">
                    <span>{t.knowledge.category}</span>
                    <CustomSelect value={newEntry.category} ariaLabel={t.knowledge.category} onChange={(value) => setNewEntry((current) => ({ ...current, category: value }))}
                      options={["streamer", "common", "style"].map((value) => ({ value, label: t.knowledge.categories[value as "streamer" | "common" | "style"] }))} />
                  </div>
                  <label className="field">
                    <span>{t.knowledge.create.key}</span>
                    <input value={newEntry.key} onChange={(event) => setNewEntry((current) => ({ ...current, key: event.target.value }))} />
                  </label>
                  {newEntry.category === "common" ? (
                    <div className="field">
                      <span>{t.knowledge.create.type}</span>
                      <CustomSelect value={newEntry.entryType} ariaLabel={t.knowledge.create.type} onChange={(value) => setNewEntry((current) => ({ ...current, entryType: value }))}
                        options={ENTRY_TYPES.map((value) => ({ value, label: t.knowledge.entryTypes[value] }))} />
                    </div>
                  ) : null}
                  <label className="field">
                    <span>{t.knowledge.create.aliases}</span>
                    <input value={newEntry.aliases} placeholder={t.knowledge.create.aliasesPlaceholder} onChange={(event) => setNewEntry((current) => ({ ...current, aliases: event.target.value }))} />
                  </label>
                  <label className="field field-span-all">
                    <span>{t.knowledge.create.intro}</span>
                    <textarea rows={3} value={newEntry.intro} onChange={(event) => setNewEntry((current) => ({ ...current, intro: event.target.value }))} />
                  </label>
                </div>
                <div className="knowledge-actions">
                  <button type="button" className="button button-secondary" onClick={() => setShowCreate(false)}>{t.knowledge.cancel}</button>
                  <button type="button" className="button button-primary" disabled={busy || !newEntry.key.trim() || !newEntry.intro.trim()} onClick={() => void createEntry()}>
                    <Plus size={15} />
                    {t.knowledge.create.action}
                  </button>
                </div>
              </div>
            ) : document ? (
              <>
                <div className="section-heading knowledge-editor-heading">
                  <div>
                    <span className="section-kicker">{t.knowledge.categories[document.category as "common" | "streamer" | "style"] || document.category} · rev {document.valid_from_rev}</span>
                    <h2>{document.key}</h2>
                    <p>{document.qualified_name}</p>
                  </div>
                  <div className="knowledge-actions">
                    <button
                      type="button"
                      className="button button-secondary button-danger-text"
                      disabled={busy}
                      onClick={() => {
                        confirmAction(`${document.key}\n\n${t.knowledge.editor.retireConfirm}`, () => {
                          void runMaintenance("retire", [document.qualified_name, "--reason", "desktop"]);
                        });
                      }}
                    >
                      {t.knowledge.editor.retire}
                    </button>
                    <button type="button" className="button button-primary" disabled={busy || draft === document.text} onClick={() => void runMaintenance("edit", [document.qualified_name], draft)}>
                      <Save size={15} />
                      {t.knowledge.editor.save}
                    </button>
                  </div>
                </div>
                <KnowledgeDocument text={draft} empty={language === "zh" ? "条目还没有正文，可展开下方编辑原文。" : "No content yet. Expand Edit source below."} />
                <details className="knowledge-source-editor" key={document.id}>
                  <summary>{language === "zh" ? "编辑原文（高级）" : "Edit source (advanced)"}{draft !== document.text ? (language === "zh" ? " · 有未保存的修改" : " · Unsaved changes") : ""}</summary>
                  <p className="field-hint">{t.knowledge.editor.hint}</p>
                  <textarea className="knowledge-document" aria-label={language === "zh" ? "条目原文" : "Entry source"} disabled={busy} value={draft} spellCheck={false} onChange={(event) => setDraft(event.target.value)} />
                </details>
                {document.category === "common" ? <details className="knowledge-source-editor"><summary>{language === "zh" ? "拆分、移动与关联条目（高级）" : "Split, move and link entries (advanced)"}</summary><KnowledgeStructure key={document.id} document={document} entries={snapshot?.entries ?? []} disabled={busy || draft !== document.text}
                  onChanged={async () => { await loadSnapshot(); const next = await desktopApi.getKnowledgeEntry(document.qualified_name); setDocument(next); setDraft(next.text); }} /></details> : null}
              </>
            ) : (
              <div className="knowledge-empty-editor">{t.knowledge.selectEntry}</div>
            )}
          </section>
        </div>
      ) : null}

      {!loading && tab === "feedback" ? (
        <div className="knowledge-stack">
          <BilingualKnowledgeImport snapshot={snapshot} tasks={tasks} routing={routing} onApplied={() => loadSnapshot()} />
          <section className="primary-panel knowledge-section">
            <div className="section-heading">
              <div><h2>{t.knowledge.feedback.title}</h2><p>{t.knowledge.feedback.hint}</p></div>
            </div>
            <div className="knowledge-action-grid">
              <div className="field">
                <span>{t.knowledge.feedback.task}</span>
                <CustomSelect disabled={busy} value={feedbackTaskId} ariaLabel={t.knowledge.feedback.task} onChange={setFeedbackTaskId}
                  options={[{ value: "", label: t.knowledge.feedback.noTask }, ...completedTasks.map((task) => ({ value: task.task_id, label: taskLabel(task) }))]} />
              </div>
              <button type="button" className="button button-secondary knowledge-form-action" disabled={busy || !feedbackTaskId} onClick={() => void loadFeedback()}>
                <BookOpenText size={15} />{t.knowledge.feedback.inspect}
              </button>
            </div>
            {feedbackError ? <p className="knowledge-error" role="alert">{feedbackError}</p> : null}
            {feedback ? (
              <div className="feedback-summary-grid">
                <article><strong>{feedback.merged_hints.length}</strong><span>{t.knowledge.feedback.hints}</span></article>
                <article><strong>{feedback.asr_corrections.length}</strong><span>{t.knowledge.feedback.corrections}</span></article>
                <article><strong>{feedback.uncertainties.length}</strong><span>{t.knowledge.feedback.uncertainties}</span></article>
                <article><strong>{feedback.windows.length}</strong><span>{t.knowledge.feedback.windows}</span></article>
                <div className="feedback-detail field-span-all">
                  {feedback.merged_hints.map((hint, index) => (
                    <div key={`${hint.category}-${hint.entry}-${index}`}>
                      <strong>{hint.category}/{hint.entry}</strong>
                      <span>{hint.focus || hint.reason || hint.direction || "—"}</span>
                    </div>
                  ))}
                  {[...feedback.asr_corrections, ...feedback.uncertainties, ...feedback.warnings].map((row, index) => <p key={`${row}-${index}`}>{row}</p>)}
                  {!feedback.merged_hints.length && !feedback.asr_corrections.length && !feedback.uncertainties.length ? <p>{t.knowledge.feedback.empty}</p> : null}
                </div>
              </div>
            ) : null}
          </section>

          <section className="primary-panel knowledge-section">
            <div className="section-heading">
              <div><h2>{t.knowledge.feedback.refinedTitle}</h2><p>{t.knowledge.feedback.refinedHint}</p></div>
            </div>
            <ol className="knowledge-steps" aria-label={language === "zh" ? "精修学习步骤" : "Refinement steps"}>
              <li>{language === "zh" ? "选择上方原任务" : "Select the task above"}</li>
              <li>{language === "zh" ? "选择人工精修 SRT" : "Choose the refined SRT"}</li>
              <li>{language === "zh" ? "生成并审阅提案" : "Generate and review"}</li>
              <li>{language === "zh" ? "确认写入知识库" : "Apply to knowledge"}</li>
            </ol>
            <div className="knowledge-source-info">
              <strong>{language === "zh" ? "原任务字幕（自动定位）" : "Original task subtitle (automatic)"}</strong>
              <p>{selectedTask ? (selectedTask.outputs?.finalSrt || selectedTask.request.output) : (language === "zh" ? "请先在上方选择已完成任务" : "Select a completed task above")}</p>
              <details className="knowledge-source-editor"><summary>{language === "zh" ? "原文件已移动？补选原任务字幕" : "Original moved? Select the task subtitle"}</summary>
                <p className="field-hint">{language === "zh" ? "选择本应用原先导出的、未经人工修改的字幕。不要重复选择下方的精修文件；任务识别材料仍从原任务目录读取。" : "Choose the app's unedited exported subtitle, not the refined file below. Evidence is still read from the original task folder."}</p>
                <div className="knowledge-file-row"><input value={sourcePath} disabled={busy} aria-label={language === "zh" ? "补选原任务字幕" : "Original task subtitle override"} placeholder={language === "zh" ? "留空：自动查找原任务与导出位置" : "Empty: locate original/export automatically"} onChange={(event) => setSourcePath(event.target.value)} /><button type="button" className="button button-secondary" disabled={busy} onClick={() => void chooseFile("source")}>{t.knowledge.browse}</button></div>
              </details>
            </div>
            <div className="knowledge-workflow-row">
              <label className="field field-span-all"><span>{language === "zh" ? "人工精修后的 SRT（必填）" : "Manually refined SRT (required)"}</span>
              <div className="knowledge-file-row">
                <input disabled={busy} value={refinedPath} placeholder={t.knowledge.feedback.refinedPlaceholder} aria-label={t.knowledge.feedback.refinedPlaceholder} onChange={(event) => setRefinedPath(event.target.value)} />
                <button type="button" disabled={busy} className="button button-secondary" onClick={() => void chooseFile("refined")}>{t.knowledge.browse}</button>
              </div>
              </label>
              {refinedError ? <div className="knowledge-error field-span-all" role="alert"><strong>{language === "zh" ? "未生成或应用提案" : "Proposal not generated or applied"}</strong><p>{refinedError}</p></div> : null}
              <div className="knowledge-actions">
                <button type="button" className="button button-secondary" disabled={busy || !selectedTask || !refinedPath.trim()} onClick={() => void applyRefined(false)}>{t.knowledge.feedback.propose}</button>
                <button type="button" className="button button-primary" disabled={busy || !canApplyProposal(refinedProposal)} onClick={() => confirmAction(t.knowledge.feedback.applyConfirm, () => void applyRefined(true))}>{language === "zh" ? "应用已审阅提案" : "Apply reviewed proposal"}</button>
              </div>
              <p className="field-hint field-span-all" role="status">{busy ? (language === "zh" ? "正在处理，请稍候…" : "Working, please wait…") : !selectedTask ? (language === "zh" ? "先在上方选择已完成任务，才能生成提案。" : "Select a completed task above first.") : !refinedPath.trim() ? (language === "zh" ? "请选择人工精修的 SRT。生成会调用模型；审阅后应用同一份提案，不再调用模型。" : "Choose a refined SRT. Generation calls a model; applying the reviewed proposal does not.") : (language === "zh" ? "文件已选择。点击“生成提案”，检查下方内容后再点击“应用已审阅提案”。" : "File selected. Generate a proposal, review it below, then apply it.")}</p>
              {refinedProposal ? <ProposalReview report={refinedProposal} /> : null}
            </div>
          </section>
        </div>
      ) : null}

      {!loading && tab === "maintenance" ? (
        <div className="knowledge-maintenance-grid">
          <KnowledgeRecovery onChanged={() => loadSnapshot(false)} />
          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.maintenance.healthTitle}</h2><p>{t.knowledge.maintenance.healthHint}</p></div></div>
            <div className="knowledge-command-row">
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("refresh")}><RefreshCw size={15} />{t.knowledge.maintenance.rebuild}</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("phase-b")}>{t.knowledge.maintenance.phasePreview}</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => confirmAction(t.knowledge.maintenance.phaseConfirm, () => void runMaintenance("phase-b", ["--execute"]))}>{t.knowledge.maintenance.phaseApply}</button>
            </div>
            <div className="knowledge-command-group">
              <strong>{t.knowledge.maintenance.verify}</strong>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("verify")}>{t.knowledge.preview}</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("verify", ["--execute"])}>{t.knowledge.run}</button>
              <button type="button" className="button button-primary" disabled={busy} onClick={() => void runMaintenance("verify", ["--execute", "--apply"])}>{t.knowledge.runAndApply}</button>
            </div>
            <div className="knowledge-command-group">
              <strong>{t.knowledge.maintenance.repair}</strong>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("repair")}>{t.knowledge.preview}</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("repair", ["--execute"])}>{t.knowledge.run}</button>
              <button type="button" className="button button-primary" disabled={busy} onClick={() => void runMaintenance("repair", ["--execute", "--apply"])}>{t.knowledge.runAndApply}</button>
            </div>
          </section>

          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.maintenance.candidates}</h2><p>{t.knowledge.maintenance.candidatesHint}</p></div></div>
            <input value={candidateReason} placeholder={t.knowledge.reason} onChange={(event) => setCandidateReason(event.target.value)} />
            <div className="knowledge-list compact">
              {(snapshot?.pending_candidates || []).map((candidate) => (
                <article key={candidate.candidate_key}>
                  <div><strong>{candidate.candidate_key}</strong><p>{String(candidate.reason || candidate.candidate || "")}</p></div>
                  <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("candidates", ["--resolve", candidate.candidate_key, "--reason", candidateReason])}>{t.knowledge.resolve}</button>
                </article>
              ))}
              {!snapshot?.pending_candidates.length ? <p className="empty-copy">{t.knowledge.maintenance.noCandidates}</p> : null}
            </div>
          </section>

          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.maintenance.revisions}</h2><p>{t.knowledge.maintenance.revisionsHint}</p></div></div>
            <div className="knowledge-list revision-list">
              {(snapshot?.revisions || []).map((revision) => (
                <article key={revision.rev}>
                  <div><strong>rev {revision.rev} · {revision.kind}</strong><p>{revision.note || revision.task_id || revision.created_at}</p></div>
                  <button type="button" className="button button-secondary button-danger-text" disabled={busy} onClick={() => confirmAction(t.knowledge.maintenance.revertConfirm.replace("{rev}", String(revision.rev)), () => void runMaintenance("revert", [String(revision.rev)]))}>{t.knowledge.maintenance.revert}</button>
                </article>
              ))}
            </div>
            <div className="knowledge-inline-form">
              <input value={restoreId} placeholder={t.knowledge.maintenance.restorePlaceholder} onChange={(event) => setRestoreId(event.target.value)} />
              <button type="button" className="button button-secondary" disabled={busy || !restoreId.trim()} onClick={() => void runMaintenance("restore", [restoreId.trim()])}>{t.knowledge.maintenance.restore}</button>
            </div>
          </section>

          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.maintenance.ingest}</h2><p>{t.knowledge.maintenance.ingestHint}</p></div></div>
            <div className="knowledge-form-grid">
              <div className="field field-span-all"><span>{t.knowledge.maintenance.subject}</span><CustomSelect disabled={busy} ariaLabel={t.knowledge.maintenance.subject} value={ingest.subject} onChange={(value) => setIngest((current) => ({ ...current, subject: value }))} options={[{ value: "", label: t.common.select }, ...(snapshot?.entries || []).map((entry) => ({ value: entry.qualified_name, label: entry.qualified_name }))]} /></div>
              <label className="field field-span-all"><span>{t.knowledge.maintenance.material}</span><div className="knowledge-file-row"><input value={ingest.material} onChange={(event) => setIngest((current) => ({ ...current, material: event.target.value }))} /><button type="button" className="button button-secondary" onClick={() => void chooseFile("material")}>{t.knowledge.browse}</button></div></label>
              <label className="field field-span-all"><span>{t.knowledge.maintenance.prompt}</span><textarea rows={3} value={ingest.prompt} onChange={(event) => setIngest((current) => ({ ...current, prompt: event.target.value }))} /></label>
            </div>
            <div className="knowledge-actions">
              <button type="button" className="button button-secondary" disabled={busy || !ingest.subject || !ingest.material} onClick={() => void runMaintenance("ingest", ["--subject", ingest.subject, "--material", ingest.material, "--prompt", ingest.prompt])}>{t.knowledge.preview}</button>
              <button type="button" className="button button-secondary" disabled={busy || !ingest.subject || !ingest.material} onClick={() => void runMaintenance("ingest", ["--subject", ingest.subject, "--material", ingest.material, "--prompt", ingest.prompt, "--execute"])}>{t.knowledge.run}</button>
              <button type="button" className="button button-primary" disabled={busy || !ingest.subject || !ingest.material} onClick={() => void runMaintenance("ingest", ["--subject", ingest.subject, "--material", ingest.material, "--prompt", ingest.prompt, "--execute", "--apply"])}>{t.knowledge.runAndApply}</button>
            </div>
          </section>
        </div>
      ) : null}

      {!loading && tab === "sharing" ? (
        <div className="knowledge-stack">
          <KnowledgeFileExchange snapshot={snapshot} selected={selectedName} onSelect={setSelectedName} busy={busy} setBusy={setBusy} onChanged={async () => {
            await loadSnapshot();
            const next = await desktopApi.getKnowledgeEntry(selectedName);
            setDocument(next); setDraft(next.text);
          }} />
          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.sharing.connection}</h2><p>{t.knowledge.sharing.connectionHint}</p></div></div>
            <p className="field-hint">{language === "zh" ? "当前地址：" : "Current address: "}<span className="knowledge-server-address">{remote.trim() || snapshot?.default_remote || (language === "zh" ? "上游默认社区" : "Upstream default community")}</span></p>
            <details className="knowledge-source-editor"><summary>{language === "zh" ? "其他服务器（可选）" : "Other server (optional)"}</summary><p className="field-hint">{language === "zh" ? "仅填写共享库维护者提供的完整 HTTP(S) 地址，不是 GitHub 仓库链接或本机文件夹。留空使用上游配置 / 内置地址。服务器是否在线及何时审核，由该社区维护者决定。" : "Use the complete HTTP(S) address from the library maintainer, not a GitHub repository URL or local folder. Leave blank for the configured/built-in default. Availability and review timing depend on that community."}</p><label className="field"><span>{t.knowledge.sharing.remote}</span><input disabled={busy} list="knowledge-remotes" value={remote} placeholder={language === "zh" ? "留空使用默认社区" : "Leave blank for the default community"} onChange={(event) => setRemote(event.target.value)} /><datalist id="knowledge-remotes">{snapshot?.registered_remotes.map((value) => <option value={value} key={value} />)}</datalist></label></details>
              <div className="knowledge-command-row">
                <button type="button" className="button button-primary" disabled={busy} onClick={() => confirmAction(language === "zh" ? "下载社区知识并合并到本地？同一字段双方都修改时保留本地版本并记录冲突，不会上传本地条目。" : "Download and merge community knowledge? Conflicting local changes are preserved and recorded. No local entries are uploaded.", () => void runShare("pull", remoteArgs))}><Download size={15} />{t.knowledge.sharing.pull}</button>
                <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runShare("register", remoteArgs)}><ShieldCheck size={15} />{t.knowledge.sharing.register}</button>
              </div>
          </section>

          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.sharing.publish}</h2><p>{t.knowledge.sharing.publishHint}</p></div></div>
            <div className="knowledge-form-grid knowledge-form-grid-three">
              <div className="field"><span>{t.knowledge.sharing.subject}</span><CustomSelect disabled={busy} ariaLabel={t.knowledge.sharing.subject} value={selectedName} onChange={setSelectedName} options={[{ value: "", label: t.common.select }, ...(snapshot?.entries || []).map((entry) => ({ value: entry.qualified_name, label: entry.qualified_name }))]} /></div>
              <details className="knowledge-source-editor field-span-all"><summary>{language === "zh" ? "筛选共享内容（可选）" : "Filter shared content (optional)"}</summary><div className="knowledge-form-grid"><label className="field"><span>{t.knowledge.sharing.kinds}</span><input disabled={busy} value={shareKinds} placeholder="note,rule" onChange={(event) => setShareKinds(event.target.value)} /></label>
              <label className="field"><span>{t.knowledge.sharing.match}</span><input disabled={busy} value={shareMatch} onChange={(event) => setShareMatch(event.target.value)} /></label></div></details>
            </div>
            <div className="knowledge-split-actions">
              <div className="knowledge-command-row">
                <button type="button" className="button button-secondary" disabled={busy || !selectedName} onClick={() => void runShare("mark", [selectedName, ...(shareKinds ? ["--kinds", shareKinds] : []), ...(shareMatch ? ["--match", shareMatch] : [])])}>{t.knowledge.sharing.mark}</button>
                <button type="button" className="button button-secondary" disabled={busy || !selectedName} onClick={() => void runShare("unmark", [selectedName, ...(shareKinds ? ["--kinds", shareKinds] : []), ...(shareMatch ? ["--match", shareMatch] : [])])}>{t.knowledge.sharing.unmark}</button>
                <button type="button" className="button button-primary" disabled={busy || !selectedName} onClick={() => confirmAction(language === "zh" ? `将「${selectedName}」中已标记可共享的内容上传至当前社区审核？请先检查正文是否含私人信息。提交不代表审核通过，也不会上传密钥或任务日志。` : `Upload marked content in ${selectedName} for community review? Check for private text first. Submission is not approval; keys and task logs are not uploaded.`, () => void runShare("push", [selectedName, ...remoteArgs]))}><Upload size={15} />{t.knowledge.sharing.push}</button>
              </div>
              <div className="knowledge-inline-form">
                <input value={queueId} inputMode="numeric" placeholder={t.knowledge.sharing.queueId} aria-label={t.knowledge.sharing.queueId} onChange={(event) => setQueueId(event.target.value)} />
                <button type="button" className="button button-secondary" disabled={busy || !/^\d+$/.test(queueId)} onClick={() => void runShare("status", [...remoteArgs, "--queue-id", queueId])}>{t.knowledge.sharing.status}</button>
              </div>
            </div>
          </section>

          <details className="primary-panel knowledge-section knowledge-sharing-advanced"><summary>{language === "zh" ? "高级：冲突处理与维护者审核" : "Advanced: conflicts and maintainer review"}</summary>
          <section className="knowledge-advanced-section">
            <div className="section-heading"><div><h2>{t.knowledge.sharing.conflicts}</h2><p>{t.knowledge.sharing.conflictsHint}</p></div></div>
            <input value={conflictReason} placeholder={t.knowledge.reason} onChange={(event) => setConflictReason(event.target.value)} />
            <div className="knowledge-list compact">
              {snapshot?.conflicts.map((conflict) => (
                <article key={conflict.conflict_id}>
                  <div><strong>{conflict.conflict_id}</strong><p>{conflict.description}</p></div>
                  <div className="knowledge-actions">
                    <button type="button" className="button button-secondary" disabled={busy || !conflictReason.trim()} onClick={() => void runShare("conflicts", ["--resolve", conflict.conflict_id, "--reason", conflictReason])}>{t.knowledge.resolve}</button>
                    <button type="button" className="button button-secondary" disabled={busy || !conflictReason.trim()} onClick={() => void runShare("conflicts", ["--dismiss", conflict.conflict_id, "--reason", conflictReason])}>{t.knowledge.dismiss}</button>
                  </div>
                </article>
              ))}
              {!snapshot?.conflicts.length ? <p className="empty-copy">{t.knowledge.sharing.noConflicts}</p> : null}
            </div>
            <div className="knowledge-command-row">
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runShare("conflicts", ["--repair", ...(remote ? ["--remote", remote] : [])])}>{t.knowledge.preview}</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runShare("conflicts", ["--repair", "--execute", ...(remote ? ["--remote", remote] : [])])}>{t.knowledge.run}</button>
              <button type="button" className="button button-primary" disabled={busy} onClick={() => void runShare("conflicts", ["--repair", "--execute", "--apply", ...(remote ? ["--remote", remote] : [])])}>{t.knowledge.runAndApply}</button>
            </div>
          </section>

          <section className="knowledge-advanced-section">
            <div className="section-heading"><div><h2>{t.knowledge.sharing.review}</h2><p>{t.knowledge.sharing.reviewHint}</p></div></div>
            <div className="knowledge-form-grid knowledge-form-grid-three">
              <label className="field"><span>{t.knowledge.sharing.maintainerToken}</span><input type="password" value={maintainer.token} onChange={(event) => setMaintainer((current) => ({ ...current, token: event.target.value }))} /></label>
              <label className="field"><span>{t.knowledge.sharing.queueId}</span><input inputMode="numeric" value={maintainer.queueId} onChange={(event) => setMaintainer((current) => ({ ...current, queueId: event.target.value }))} /></label>
              <label className="field"><span>{t.knowledge.sharing.override}</span><input value={maintainer.override} onChange={(event) => setMaintainer((current) => ({ ...current, override: event.target.value }))} /></label>
            </div>
            <div className="knowledge-command-row">
              {(["preview", "run", "post"] as const).map((mode) => {
                const args = ["--remote", remote.trim() || snapshot?.default_remote || "", "--maintainer-token", maintainer.token];
                if (maintainer.queueId) args.push("--queue-id", maintainer.queueId);
                if (mode !== "preview") args.push("--execute");
                if (mode === "post") args.push("--post");
                if (maintainer.override) args.push("--override-thresholds", maintainer.override);
                return <button type="button" key={mode} className={`button ${mode === "post" ? "button-primary" : "button-secondary"}`} disabled={busy || !(remote.trim() || snapshot?.default_remote) || !maintainer.token} onClick={() => void runShare("review", args)}>{mode === "preview" ? t.knowledge.preview : mode === "run" ? t.knowledge.run : t.knowledge.sharing.post}</button>;
              })}
            </div>
          </section>
          </details>
        </div>
      ) : null}

      {output ? (
        <section className="primary-panel knowledge-output">
          <div className="section-heading"><div><h2>{t.knowledge.output}</h2><p>{t.knowledge.outputHint}</p></div><button type="button" className="button button-secondary" onClick={() => setOutput("")}>{t.knowledge.clear}</button></div>
          <pre>{output}</pre>
        </section>
      ) : null}
      <ConfirmDialog config={{ id: "knowledge-action", title: language === "zh" ? "确认知识库操作" : "Confirm knowledge operation", message: confirmation?.message || "", allowRemember: false, tone: "danger" }} open={Boolean(confirmation)} onCancel={() => setConfirmation(null)} onConfirm={() => { const action = confirmation?.action; setConfirmation(null); action?.(); }} />
      {busy ? <div className="knowledge-busy" role="status"><RefreshCw size={15} />{t.knowledge.running}</div> : null}
    </div>
  );
}
