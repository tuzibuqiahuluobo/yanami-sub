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
import type {
  JobSnapshot,
  KnowledgeEntryDocument,
  KnowledgeFeedback,
  KnowledgeMaintenanceCommand,
  KnowledgeShareCommand,
  KnowledgeSnapshot,
  TaskRequest,
} from "@/lib/types";

import { useLanguage } from "./LanguageProvider";


type KnowledgeTab = "library" | "feedback" | "maintenance" | "sharing";

interface KnowledgeCenterProps {
  tasks: JobSnapshot[];
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


export function KnowledgeCenter({ tasks }: KnowledgeCenterProps) {
  const { t } = useLanguage();
  const [tab, setTab] = useState<KnowledgeTab>("library");
  const [snapshot, setSnapshot] = useState<KnowledgeSnapshot | null>(null);
  const [document, setDocument] = useState<KnowledgeEntryDocument | null>(null);
  const [draft, setDraft] = useState("");
  const [selectedName, setSelectedName] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");

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

  const [candidateReason, setCandidateReason] = useState("");
  const [restoreId, setRestoreId] = useState("");
  const [ingest, setIngest] = useState({ subject: "", material: "", prompt: "" });

  const [remote, setRemote] = useState("");
  const [shareKinds, setShareKinds] = useState("");
  const [shareMatch, setShareMatch] = useState("");
  const [queueId, setQueueId] = useState("");
  const [conflictReason, setConflictReason] = useState("");
  const [maintainer, setMaintainer] = useState({ token: "", queueId: "", override: "" });

  const loadSnapshot = async (keepSelection = true) => {
    setError("");
    const next = await desktopApi.getKnowledgeSnapshot();
    setSnapshot(next);
    if (!remote && next.registered_remotes.length) setRemote(next.registered_remotes[0]);
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
      return result;
    } catch (reason) {
      setError(errorMessage(reason));
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
    setError("");
    try {
      setFeedback(await desktopApi.getTaskKnowledgeFeedback(feedbackTaskId));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  const chooseFile = async (target: "refined" | "material") => {
    try {
      const chosen = await desktopApi.selectInputFile();
      if (!chosen.path) return;
      if (target === "refined") setRefinedPath(chosen.path);
      else setIngest((current) => ({ ...current, material: chosen.path || "" }));
    } catch (reason) {
      setError(errorMessage(reason));
    }
  };

  const applyRefined = async (apply: boolean) => {
    if (!selectedTask || !refinedPath.trim()) return;
    if (apply && !window.confirm(t.knowledge.feedback.applyConfirm)) return;
    setBusy(true);
    setError("");
    try {
      const report = await desktopApi.runRefinedKnowledgeUpdate({
        task_id: selectedTask.task_id,
        refined_srt: refinedPath.trim(),
        task_summary: selectedTask.request.task_summary,
        llm_model: selectedTask.request.llm_model,
        apply,
        resume: true,
      });
      setOutput(JSON.stringify(report, null, 2));
      await loadSnapshot();
    } catch (reason) {
      setError(errorMessage(reason));
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
              onClick={() => setTab(item.id)}
            >
              <Icon size={15} />
              {item.label}
            </button>
          );
        })}
      </div>

      {error ? <div className="inline-error knowledge-error">{error}</div> : null}
      {loading ? <div className="primary-panel knowledge-loading">{t.knowledge.loading}</div> : null}

      {!loading && tab === "library" ? (
        <div className="knowledge-library">
          <aside className="primary-panel knowledge-browser">
            <div className="knowledge-browser-tools">
              <label className="knowledge-search">
                <Search size={15} />
                <input value={search} placeholder={t.knowledge.search} onChange={(event) => setSearch(event.target.value)} />
              </label>
              <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label={t.knowledge.category}>
                <option value="all">{t.knowledge.categories.all}</option>
                <option value="streamer">{t.knowledge.categories.streamer}</option>
                <option value="common">{t.knowledge.categories.common}</option>
                <option value="style">{t.knowledge.categories.style}</option>
              </select>
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
                  onClick={() => setSelectedName(entry.qualified_name)}
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
                  <label className="field">
                    <span>{t.knowledge.category}</span>
                    <select value={newEntry.category} onChange={(event) => setNewEntry((current) => ({ ...current, category: event.target.value }))}>
                      <option value="streamer">{t.knowledge.categories.streamer}</option>
                      <option value="common">{t.knowledge.categories.common}</option>
                      <option value="style">{t.knowledge.categories.style}</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>{t.knowledge.create.key}</span>
                    <input value={newEntry.key} onChange={(event) => setNewEntry((current) => ({ ...current, key: event.target.value }))} />
                  </label>
                  {newEntry.category === "common" ? (
                    <label className="field">
                      <span>{t.knowledge.create.type}</span>
                      <select value={newEntry.entryType} onChange={(event) => setNewEntry((current) => ({ ...current, entryType: event.target.value }))}>
                        {ENTRY_TYPES.map((value) => <option value={value} key={value}>{t.knowledge.entryTypes[value]}</option>)}
                      </select>
                    </label>
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
                    <span className="section-kicker">{document.category} · rev {document.valid_from_rev}</span>
                    <h2>{document.key}</h2>
                    <p>{document.qualified_name}</p>
                  </div>
                  <div className="knowledge-actions">
                    <button
                      type="button"
                      className="button button-secondary button-danger-text"
                      disabled={busy}
                      onClick={() => {
                        if (window.confirm(t.knowledge.editor.retireConfirm)) {
                          void runMaintenance("retire", [document.qualified_name, "--reason", "desktop"]);
                        }
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
                <textarea className="knowledge-document" value={draft} spellCheck={false} onChange={(event) => setDraft(event.target.value)} />
                <p className="field-hint">{t.knowledge.editor.hint}</p>
              </>
            ) : (
              <div className="knowledge-empty-editor">{t.knowledge.selectEntry}</div>
            )}
          </section>
        </div>
      ) : null}

      {!loading && tab === "feedback" ? (
        <div className="knowledge-stack">
          <section className="primary-panel knowledge-section">
            <div className="section-heading">
              <div><h2>{t.knowledge.feedback.title}</h2><p>{t.knowledge.feedback.hint}</p></div>
            </div>
            <div className="knowledge-action-grid">
              <label className="field">
                <span>{t.knowledge.feedback.task}</span>
                <select value={feedbackTaskId} onChange={(event) => { setFeedbackTaskId(event.target.value); setFeedback(null); }}>
                  <option value="">{t.knowledge.feedback.noTask}</option>
                  {completedTasks.map((task) => <option key={task.task_id} value={task.task_id}>{taskLabel(task)}</option>)}
                </select>
              </label>
              <button type="button" className="button button-secondary knowledge-form-action" disabled={busy || !feedbackTaskId} onClick={() => void loadFeedback()}>
                <BookOpenText size={15} />{t.knowledge.feedback.inspect}
              </button>
            </div>
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
            <div className="knowledge-workflow-row">
              <div className="knowledge-file-row">
                <input value={refinedPath} placeholder={t.knowledge.feedback.refinedPlaceholder} aria-label={t.knowledge.feedback.refinedPlaceholder} onChange={(event) => setRefinedPath(event.target.value)} />
                <button type="button" className="button button-secondary" onClick={() => void chooseFile("refined")}>{t.knowledge.browse}</button>
              </div>
              <div className="knowledge-actions">
                <button type="button" className="button button-secondary" disabled={busy || !selectedTask || !refinedPath.trim()} onClick={() => void applyRefined(false)}>{t.knowledge.feedback.propose}</button>
                <button type="button" className="button button-primary" disabled={busy || !selectedTask || !refinedPath.trim()} onClick={() => void applyRefined(true)}>{t.knowledge.feedback.apply}</button>
              </div>
            </div>
          </section>
        </div>
      ) : null}

      {!loading && tab === "maintenance" ? (
        <div className="knowledge-maintenance-grid">
          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.maintenance.healthTitle}</h2><p>{t.knowledge.maintenance.healthHint}</p></div></div>
            <div className="knowledge-command-row">
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("refresh")}><RefreshCw size={15} />{t.knowledge.maintenance.rebuild}</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => void runMaintenance("phase-b")}>{t.knowledge.maintenance.phasePreview}</button>
              <button type="button" className="button button-secondary" disabled={busy} onClick={() => { if (window.confirm(t.knowledge.maintenance.phaseConfirm)) void runMaintenance("phase-b", ["--execute"]); }}>{t.knowledge.maintenance.phaseApply}</button>
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
                  <button type="button" className="button button-secondary button-danger-text" disabled={busy} onClick={() => { if (window.confirm(t.knowledge.maintenance.revertConfirm.replace("{rev}", String(revision.rev)))) void runMaintenance("revert", [String(revision.rev)]); }}>{t.knowledge.maintenance.revert}</button>
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
              <label className="field field-span-all"><span>{t.knowledge.maintenance.subject}</span><select value={ingest.subject} onChange={(event) => setIngest((current) => ({ ...current, subject: event.target.value }))}><option value="">{t.common.select}</option>{snapshot?.entries.map((entry) => <option value={entry.qualified_name} key={entry.id}>{entry.qualified_name}</option>)}</select></label>
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
          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.sharing.connection}</h2><p>{t.knowledge.sharing.connectionHint}</p></div></div>
            <div className="knowledge-connection-row">
              <label className="field"><span>{t.knowledge.sharing.remote}</span><input list="knowledge-remotes" value={remote} placeholder="https://…" onChange={(event) => setRemote(event.target.value)} /><datalist id="knowledge-remotes">{snapshot?.registered_remotes.map((value) => <option value={value} key={value} />)}</datalist></label>
              <div className="knowledge-command-row">
                <button type="button" className="button button-secondary" disabled={busy || !remote.trim()} onClick={() => void runShare("register", ["--remote", remote.trim()])}><ShieldCheck size={15} />{t.knowledge.sharing.register}</button>
                <button type="button" className="button button-secondary" disabled={busy || !remote.trim()} onClick={() => void runShare("pull", ["--remote", remote.trim()])}><Download size={15} />{t.knowledge.sharing.pull}</button>
              </div>
            </div>
          </section>

          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.sharing.publish}</h2><p>{t.knowledge.sharing.publishHint}</p></div></div>
            <div className="knowledge-form-grid knowledge-form-grid-three">
              <label className="field"><span>{t.knowledge.sharing.subject}</span><select value={selectedName} onChange={(event) => setSelectedName(event.target.value)}><option value="">{t.common.select}</option>{snapshot?.entries.map((entry) => <option key={entry.id} value={entry.qualified_name}>{entry.qualified_name}</option>)}</select></label>
              <label className="field"><span>{t.knowledge.sharing.kinds}</span><input value={shareKinds} placeholder="note,rule" onChange={(event) => setShareKinds(event.target.value)} /></label>
              <label className="field"><span>{t.knowledge.sharing.match}</span><input value={shareMatch} onChange={(event) => setShareMatch(event.target.value)} /></label>
            </div>
            <div className="knowledge-split-actions">
              <div className="knowledge-command-row">
                <button type="button" className="button button-secondary" disabled={busy || !selectedName} onClick={() => void runShare("mark", [selectedName, ...(shareKinds ? ["--kinds", shareKinds] : []), ...(shareMatch ? ["--match", shareMatch] : [])])}>{t.knowledge.sharing.mark}</button>
                <button type="button" className="button button-secondary" disabled={busy || !selectedName} onClick={() => void runShare("unmark", [selectedName, ...(shareKinds ? ["--kinds", shareKinds] : []), ...(shareMatch ? ["--match", shareMatch] : [])])}>{t.knowledge.sharing.unmark}</button>
                <button type="button" className="button button-primary" disabled={busy || !selectedName || !remote.trim()} onClick={() => void runShare("push", [selectedName, "--remote", remote.trim()])}><Upload size={15} />{t.knowledge.sharing.push}</button>
              </div>
              <div className="knowledge-inline-form">
                <input value={queueId} inputMode="numeric" placeholder={t.knowledge.sharing.queueId} aria-label={t.knowledge.sharing.queueId} onChange={(event) => setQueueId(event.target.value)} />
                <button type="button" className="button button-secondary" disabled={busy || !remote.trim() || !queueId} onClick={() => void runShare("status", ["--remote", remote.trim(), "--queue-id", queueId])}>{t.knowledge.sharing.status}</button>
              </div>
            </div>
          </section>

          <section className="primary-panel knowledge-section">
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

          <section className="primary-panel knowledge-section">
            <div className="section-heading"><div><h2>{t.knowledge.sharing.review}</h2><p>{t.knowledge.sharing.reviewHint}</p></div></div>
            <div className="knowledge-form-grid knowledge-form-grid-three">
              <label className="field"><span>{t.knowledge.sharing.maintainerToken}</span><input type="password" value={maintainer.token} onChange={(event) => setMaintainer((current) => ({ ...current, token: event.target.value }))} /></label>
              <label className="field"><span>{t.knowledge.sharing.queueId}</span><input inputMode="numeric" value={maintainer.queueId} onChange={(event) => setMaintainer((current) => ({ ...current, queueId: event.target.value }))} /></label>
              <label className="field"><span>{t.knowledge.sharing.override}</span><input value={maintainer.override} onChange={(event) => setMaintainer((current) => ({ ...current, override: event.target.value }))} /></label>
            </div>
            <div className="knowledge-command-row">
              {(["preview", "run", "post"] as const).map((mode) => {
                const args = ["--remote", remote.trim(), "--maintainer-token", maintainer.token];
                if (maintainer.queueId) args.push("--queue-id", maintainer.queueId);
                if (mode !== "preview") args.push("--execute");
                if (mode === "post") args.push("--post");
                if (maintainer.override) args.push("--override-thresholds", maintainer.override);
                return <button type="button" key={mode} className={`button ${mode === "post" ? "button-primary" : "button-secondary"}`} disabled={busy || !remote.trim() || !maintainer.token} onClick={() => void runShare("review", args)}>{mode === "preview" ? t.knowledge.preview : mode === "run" ? t.knowledge.run : t.knowledge.sharing.post}</button>;
              })}
            </div>
          </section>
        </div>
      ) : null}

      {output ? (
        <section className="primary-panel knowledge-output">
          <div className="section-heading"><div><h2>{t.knowledge.output}</h2><p>{t.knowledge.outputHint}</p></div><button type="button" className="button button-secondary" onClick={() => setOutput("")}>{t.knowledge.clear}</button></div>
          <pre>{output}</pre>
        </section>
      ) : null}
      {busy ? <div className="knowledge-busy" role="status"><RefreshCw size={15} />{t.knowledge.running}</div> : null}
    </div>
  );
}
