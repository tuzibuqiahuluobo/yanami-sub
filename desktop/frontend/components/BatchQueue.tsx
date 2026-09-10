"use client";

import {
  ArrowDown,
  ArrowUp,
  ExternalLink,
  FilePlus2,
  FolderOpen,
  Link2,
  ListRestart,
  Play,
  ScrollText,
  Square,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { BridgeCallError, desktopApi } from "@/lib/bridge";
import { readProcessingDevice, requestDeviceFields } from "@/lib/processingDevice";
import type {
  BatchRequest,
  BatchSnapshot,
  CapabilityState,
  RoutingSettings,
  TaskRequest,
} from "@/lib/types";

import { useLanguage } from "./LanguageProvider";
import { TaskSettings } from "./TaskSettings";


interface BatchQueueProps {
  request: Omit<TaskRequest, "input">;
  capabilities: CapabilityState;
  routing?: RoutingSettings;
  onRequestChange: (changes: Partial<Omit<TaskRequest, "input">>) => void;
  onOpenResources: () => void;
}


function addUnique(current: string[], incoming: string[]): string[] {
  const seen = new Set(current.map((item) => item.toLocaleLowerCase()));
  return [
    ...current,
    ...incoming
      .map((item) => item.trim())
      .filter((item) => item && !seen.has(item.toLocaleLowerCase()))
      .filter((item) => {
        seen.add(item.toLocaleLowerCase());
        return true;
      }),
  ];
}


function sourceLabel(source: string): string {
  try {
    const url = new URL(source);
    return url.hostname + (url.pathname === "/" ? "" : url.pathname);
  } catch {
    return source.split(/[\\/]/).pop() || source;
  }
}


export function BatchQueue({
  request,
  capabilities,
  routing,
  onRequestChange,
  onOpenResources,
}: BatchQueueProps) {
  const { t } = useLanguage();
  const [sources, setSources] = useState<string[]>([]);
  const [urlDraft, setUrlDraft] = useState("");
  const [snapshot, setSnapshot] = useState<BatchSnapshot | null>(null);
  const [history, setHistory] = useState<BatchSnapshot[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; action?: string | null } | null>(null);
  const [workers, setWorkers] = useState({ download: 2, asr: 1, llm: 2 });
  const [retryFailed, setRetryFailed] = useState(1);

  const refreshHistory = async () => {
    try {
      setHistory(await desktopApi.listBatches());
    } catch {
      // History is ancillary. Keep the last useful view if one poll fails.
    }
  };

  useEffect(() => {
    let active = true;
    void Promise.all([desktopApi.getBatchSnapshot(), desktopApi.listBatches()])
      .then(([current, rows]) => {
        if (active) {
          setSnapshot(current);
          setHistory(rows);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (snapshot?.state !== "running") return;
    let active = true;
    let inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const current = await desktopApi.getBatchSnapshot();
        if (active && current) {
          setSnapshot(current);
          if (current.state !== "running") void refreshHistory();
        }
      } catch {
        // A transient bridge failure must not erase visible progress.
      } finally {
        inFlight = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 700);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [snapshot?.state, snapshot?.batch_id]);

  const counts = useMemo(() => {
    const rows = snapshot?.items ?? [];
    return {
      done: rows.filter((item) => item.state === "done").length,
      failed: rows.filter((item) => item.state === "failed").length,
      active: rows.filter((item) => ["running", "queued"].includes(item.state)).length,
    };
  }, [snapshot]);

  const selectFiles = async () => {
    setError(null);
    try {
      const result = await desktopApi.selectBatchFiles();
      setSources((current) => addUnique(current, result.paths));
    } catch (caught) {
      setError({ message: caught instanceof Error ? caught.message : t.batch.errors.select });
    }
  };

  const addUrls = () => {
    const rows = urlDraft.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    setSources((current) => addUnique(current, rows));
    setUrlDraft("");
  };

  const move = (index: number, offset: number) => {
    const target = index + offset;
    if (target < 0 || target >= sources.length) return;
    setSources((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const start = async () => {
    if (!sources.length) return;
    setBusy(true);
    setError(null);
    try {
      const device = requestDeviceFields(readProcessingDevice());
      const payload: BatchRequest = {
        items: sources.map((input, index) => ({
          ...request,
          ...device,
          input,
          output: null,
          name: "",
          group: "",
          priority: sources.length - index,
        })),
        workers,
        asr_queue_size: 4,
        retry_failed: retryFailed,
      };
      setSnapshot(await desktopApi.startBatch(payload));
      void refreshHistory();
    } catch (caught) {
      setError({
        message: caught instanceof Error ? caught.message : t.batch.errors.start,
        action: caught instanceof BridgeCallError ? caught.action : null,
      });
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (!snapshot) return;
    setBusy(true);
    try {
      setSnapshot(await desktopApi.cancelBatch(snapshot.batch_id));
      void refreshHistory();
    } catch (caught) {
      setError({ message: caught instanceof Error ? caught.message : t.batch.errors.cancel });
    } finally {
      setBusy(false);
    }
  };

  const resume = async () => {
    if (!snapshot) return;
    setBusy(true);
    setError(null);
    try {
      setSnapshot(await desktopApi.resumeBatch(snapshot.batch_id));
    } catch (caught) {
      setError({
        message: caught instanceof Error ? caught.message : t.batch.errors.resume,
        action: caught instanceof BridgeCallError ? caught.action : null,
      });
    } finally {
      setBusy(false);
    }
  };

  const showBuilder = snapshot === null;
  return (
    <div className="page page-batch">
      <header className="page-header">
        <div>
          <h1>{t.batch.title}</h1>
          <p>{t.batch.description}</p>
        </div>
        {snapshot ? (
          <button type="button" className="button button-secondary" onClick={() => void desktopApi.openBatchDirectory(snapshot.batch_id)}>
            <FolderOpen size={15} />
            {t.batch.openFolder}
          </button>
        ) : null}
      </header>

      {showBuilder ? (
        <div className="batch-layout">
          <section className="primary-panel batch-builder">
            <div className="section-heading">
              <div>
                <h2>{t.batch.sourcesTitle}</h2>
                <p>{t.batch.sourcesHint}</p>
              </div>
              <button type="button" className="button button-secondary" onClick={() => void selectFiles()}>
                <FilePlus2 size={15} />
                {t.batch.addFiles}
              </button>
            </div>

            <div className="batch-url-row">
              <textarea
                value={urlDraft}
                rows={2}
                placeholder={t.batch.urlPlaceholder}
                onChange={(event) => setUrlDraft(event.target.value)}
              />
              <button type="button" className="button button-secondary" disabled={!urlDraft.trim()} onClick={addUrls}>
                <Link2 size={15} />
                {t.batch.addUrls}
              </button>
            </div>

            {sources.length ? (
              <ol className="batch-source-list">
                {sources.map((source, index) => (
                  <li key={source}>
                    <span className="batch-source-index">{index + 1}</span>
                    <span className="batch-source-name" title={source}>
                      <strong>{sourceLabel(source)}</strong>
                      <small>{source}</small>
                    </span>
                    <span className="batch-source-actions">
                      <button type="button" aria-label={t.batch.moveUp} disabled={index === 0} onClick={() => move(index, -1)}><ArrowUp size={14} /></button>
                      <button type="button" aria-label={t.batch.moveDown} disabled={index === sources.length - 1} onClick={() => move(index, 1)}><ArrowDown size={14} /></button>
                      <button type="button" aria-label={t.batch.remove} onClick={() => setSources((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}><Trash2 size={14} /></button>
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="batch-empty">{t.batch.empty}</div>
            )}

            <div className="panel-divider" />
            <div className="section-heading"><h2>{t.batch.settingsTitle}</h2></div>
            <TaskSettings
              request={request}
              capabilities={capabilities}
              routing={routing}
              disabled={busy}
              batchMode
              onChange={onRequestChange}
            />

            <div className="batch-workers">
              {(["download", "asr", "llm"] as const).map((name) => (
                <label className="field" key={name}>
                  <span>{t.batch.workers[name]}</span>
                  <input
                    type="number"
                    min={1}
                    max={name === "asr" ? 4 : 8}
                    value={workers[name]}
                    onChange={(event) => setWorkers((current) => ({ ...current, [name]: Math.max(1, Number(event.target.value) || 1) }))}
                  />
                </label>
              ))}
              <label className="field">
                <span>{t.batch.retryFailed}</span>
                <input type="number" min={0} max={10} value={retryFailed} onChange={(event) => setRetryFailed(Math.max(0, Number(event.target.value) || 0))} />
              </label>
            </div>

            {error ? (
              <div className="error-banner" role="alert">
                <strong>{error.message}</strong>
                {error.action === "open_resources" ? <button type="button" className="text-button" onClick={onOpenResources}>{t.batch.openResources}</button> : null}
              </div>
            ) : null}

            <div className="task-actions">
              <div><strong>{t.batch.ready.replace("{count}", String(sources.length))}</strong><span>{t.batch.priorityHint}</span></div>
              <button type="button" className="button button-primary" disabled={!sources.length || busy} onClick={() => void start()}>
                <Play size={15} />
                {busy ? t.batch.starting : t.batch.start}
              </button>
            </div>
          </section>
        </div>
      ) : snapshot ? (
        <section className="primary-panel batch-progress">
          <div className="batch-summary">
            <div>
              <span className={`batch-state is-${snapshot.state}`}>{t.batch.states[snapshot.state]}</span>
              <h2>{t.batch.summary.replace("{done}", String(counts.done)).replace("{total}", String(snapshot.items.length))}</h2>
              <p>{counts.failed ? t.batch.failedCount.replace("{count}", String(counts.failed)) : t.batch.runningHint.replace("{count}", String(counts.active))}</p>
            </div>
            <div className="batch-summary-actions">
              <button type="button" className="button button-secondary" onClick={() => void desktopApi.openBatchLog(snapshot.batch_id)}><ScrollText size={15} />{t.batch.openLog}</button>
              {snapshot.state === "running" ? (
                <button type="button" className="button button-danger" disabled={busy} onClick={() => void cancel()}><Square size={14} />{t.batch.cancel}</button>
              ) : (
                <button type="button" className="button button-secondary" disabled={busy || (snapshot.state === "completed" && counts.failed === 0)} onClick={() => void resume()}><ListRestart size={15} />{t.batch.resume}</button>
              )}
            </div>
          </div>

          {snapshot.error ? <div className="error-banner" role="alert"><strong>{snapshot.error}</strong></div> : null}
          {error ? <div className="error-banner" role="alert"><strong>{error.message}</strong></div> : null}

          <div className="batch-item-list">
            {snapshot.items.map((item) => (
              <article className={`batch-item is-${item.state}`} key={`${snapshot.batch_id}-${item.index}`}>
                <span className="batch-source-index">{item.index + 1}</span>
                <div className="batch-item-main">
                  <strong>{item.label}</strong>
                  <small title={item.input}>{item.error || (item.stage ? `${t.batch.stage}: ${item.stage}` : item.input)}</small>
                </div>
                <span className={`resource-label is-${item.state === "done" ? "ready" : item.state === "failed" ? "failed" : "neutral"}`}>{t.batch.itemStates[item.state]}</span>
                {Object.entries(item.outputs).map(([name, path]) => (
                  <button type="button" className="icon-button" title={`${name}: ${path}`} key={name} onClick={() => void desktopApi.openBatchOutput(snapshot.batch_id, path)}><ExternalLink size={14} /></button>
                ))}
              </article>
            ))}
          </div>

          <div className="task-actions">
            <button type="button" className="button button-secondary" disabled={snapshot.state === "running"} onClick={() => { setSnapshot(null); setSources([]); setError(null); }}>
              <FilePlus2 size={15} />{t.batch.newBatch}
            </button>
          </div>
        </section>
      ) : null}

      {history.length ? (
        <section className="batch-history">
          <div className="section-heading"><h2>{t.batch.recent}</h2></div>
          <div className="batch-history-list">
            {history.slice(0, 8).map((row) => (
              <button type="button" key={row.batch_id} className={snapshot?.batch_id === row.batch_id ? "is-active" : ""} onClick={() => setSnapshot(row)}>
                <span><strong>{row.batch_id}</strong><small>{row.items.length} {t.batch.items}</small></span>
                <span className={`batch-state is-${row.state}`}>{t.batch.states[row.state]}</span>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
