export type Route =
  | "new-task"
  | "batch"
  | "history"
  | "knowledge"
  | "resources"
  | "settings";

export type PipelineStage =
  | "vocal"
  | "aligned"
  | "stable"
  | "raw-srt"
  | "translated-srt"
  | "final-srt";

export interface BridgeError {
  code: string;
  message: string;
  action?: string | null;
}

export type ApiEnvelope<T> =
  | { ok: true; data: T }
  | { ok: false; error: BridgeError };

export interface CapabilityState {
  raw_srt: boolean;
  translation: boolean;
  web_search: boolean;
}

export type ApiProvider = "gemini_free" | "gemini_paid" | "exa" | "tavily";

export interface PublicSettings {
  api_keys: Record<ApiProvider, "configured" | "missing">;
}

export interface RevealedApiKeyEntry {
  /** User-chosen label from the .env container ("" for unnamed entries). */
  name: string;
  key: string;
  masked: string;
}

export type RevealedApiKeys = Record<
  ApiProvider,
  RevealedApiKeyEntry[]
>;

export interface RoutingPresetSummary {
  id: string;
  name: string;
  active: boolean;
  test_target_id: string;
  uses_local_agent: boolean;
  warnings: string[];
}

export interface RoutingProviderSummary {
  id: string;
  kind: string;
  base_url: string;
  key_env: string;
  configured: boolean;
}

export interface RoutingTargetSummary {
  id: string;
  display_name: string;
  backend: string;
  provider_tier: string;
  api_model_id: string;
  supports_audio: boolean;
  supports_video: boolean;
  supports_native_search: boolean;
  is_free: boolean;
  quality_score: number;
}

export interface RoutingSettings {
  active_preset_id: string;
  execution_policy: string;
  local_agent_timeout_seconds: number;
  local_agent_allow_unisolated_user_config: boolean;
  local_agent_service_tier: "" | "fast" | "flex";
  local_agent_reasoning_effort: "" | "low" | "medium" | "high" | "xhigh";
  local_agent_max_parallel: number;
  presets: RoutingPresetSummary[];
  policies: string[];
  providers: RoutingProviderSummary[];
  targets: RoutingTargetSummary[];
  model_groups: Record<string, string[]>;
  task_groups: string[];
  local_agent_bound: boolean;
  config_path: string;
  error: string;
}

export interface RoutingUpdate {
  preset: string;
  execution_policy: string;
  local_agent_timeout_seconds: number;
  local_agent_allow_unisolated_user_config: boolean;
  local_agent_service_tier: "" | "fast" | "flex";
  local_agent_reasoning_effort: "" | "low" | "medium" | "high" | "xhigh";
  local_agent_max_parallel: number;
}

export interface LocalAgentStatus {
  provider_tier: string;
  driver: string;
  models: string[];
  quota_pools: string[];
  status: "ready" | "missing" | "broken" | "unusable" | "error";
  available: boolean;
  version: string;
  detail: string;
}

export interface ResourceStatus {
  id: string;
  version: string;
  /** "outdated" is installed and usable, just not the newest version. */
  state: "missing" | "downloading" | "outdated" | "ready" | "failed";
  /** What is on disk when `state` is "outdated"; `version` is what it should be. */
  installed_version?: string;
  detail?: string;
  /** On-demand tools: listed so they are reachable, but not part of "ready". */
  optional?: boolean;
  /** A usable system Python was found, so only AI deps need installing.
   *  Structured because the UI used to sniff `detail` for a Chinese
   *  sentence written in environment.py -- rewording it there silently
   *  removed the affordance here. */
  reuses_system_python?: boolean;
  /** Another resource must be installed first; the action is disabled until then. */
  blocked_by?: string;
}

export interface ResourceInstallSnapshot {
  resource_id: string;
  resource_version: string;
  state: "queued" | "running" | "paused" | "ready" | "failed";
  phase:
    | "waiting"
    | "downloading"
    | "verifying"
    | "extracting"
    | "installing_python"
    | "creating_environment"
    | "installing_dependencies"
    | "activating"
    | "complete";
  message: string;
  downloaded: number;
  total: number;
  bytes_per_second: number;
  cache_path: string;
  install_path: string;
  logs: string[];
  error: string;
  started_at: number;
  updated_at: number;
}

export interface WorkerEvent {
  type: "started" | "stage" | "log" | "completed" | "failed" | "cancelled";
  task_id: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

// What class of GPU this machine has -- NOT a cap on what a run may use.
// `auto` asks the driver and is the default; the named tiers are for
// "leave some of the card to something else".
export type GpuTier =
  | "auto"
  | "cpu"
  | "entry"
  | "standard"
  | "standard_large_vram"
  | "high";

export interface TaskRequest {
  input: string;
  output?: string | null;
  /** Bare stem, the CLI's --name: produces out/<name>/<name>.srt. */
  name: string;
  /** Off by default: the run directory is what makes a rerun cheap. */
  cleanup_intermediate: boolean;
  stage: PipelineStage;
  model_name: string;
  /**
   * Omitted / null = "not chosen"; the backend signature holds the default.
   * It has to stay expressible: `gpu_tier: "cpu"` plus an explicit
   * `device: "cuda"` is a contradiction the worker refuses, and a front end
   * that always sends a device would either trip that refusal on every CPU-tier
   * task or force the backend to guess which half the user meant.
   */
  device?: "cuda" | "cpu" | null;
  /** Which card, on a machine with several. null lets CUDA choose. */
  gpu_index?: number | null;
  /** The card that index meant when it was picked; indexes are not identities. */
  gpu_name?: string;
  language?: string | null;
  gpu_tier: GpuTier;
  gap_sec: number;
  separator_sample_rate?: 44100 | 32000 | 22050 | null;
  separate?: boolean | null;
  vad_silero_assist?: boolean | null;
  qwen_verify: "auto" | "on" | "off";
  lang_redecode: "auto" | "on" | "off";
  asr_decode_batch: number | "auto";
  asr_context: "off" | "terms" | "full";
  word: boolean;
  asr_stabilize_profile: -1 | 0 | 1 | 2;
  /** One-run override of the shared subtitle-length knob; null follows it. */
  split_length_scale?: number | null;
  llm_media: "text" | "audio" | "video";
  llm_correction_media: "" | "text" | "audio" | "video";
  llm_planning_media: "" | "text" | "audio" | "video";
  llm_retrieval: "none" | "local" | "native";
  llm_difficulty: "quality" | "intermediate" | "efficiency";
  llm_continuity: "serial" | "parallel";
  llm_parallel_windows: number;
  llm_fast: "auto" | "on" | "off";
  llm_output_scale: number;
  /** Repeatable core --llm-model values, optionally task-group qualified. */
  llm_model: string[];
  llm_video?: string | null;
  extra_info: string;
  extra_style: string;
  task_summary?: string;
  style?: string | null;
  style_mode?: "none" | "read" | "update" | null;
  download_video_source: boolean;
  knowledge: "none" | "collect" | "update";
  refined_srt?: string | null;
  postprocess_profile: -1 | 0 | 1 | 2 | 3 | 4;
  max_retries_per_window: number;
  max_replacements_per_window: number;
  resume: boolean;
}

export interface JobSnapshot {
  task_id?: string;
  taskId?: string;
  state:
    | "idle"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "interrupted";
  request?: TaskRequest;
  events: WorkerEvent[];
  outputs?: Record<string, string>;
  error?: string | null;
  created_at?: number;
  updated_at?: number;
}

export interface Gpu {
  index: number;
  name: string;
  memory_mb: number;
}

export interface GpuSnapshot {
  /** "scanning" until the background probe answers; it is never waited on. */
  state: "scanning" | "ready" | "unavailable";
  devices: Gpu[];
}

export interface BatchItemRequest extends TaskRequest {
  group: string;
  priority: number;
}

export interface BatchWorkers {
  download: number;
  asr: number;
  llm: number;
}

export interface BatchRequest {
  items: BatchItemRequest[];
  workers: BatchWorkers;
  asr_queue_size: number;
  retry_failed: number;
}

export interface BatchItemSnapshot {
  index: number;
  input: string;
  label: string;
  state: "queued" | "running" | "done" | "failed" | "skipped" | "dropped";
  stage: string;
  error: string;
  outputs: Record<string, string>;
}

export interface BatchSnapshot {
  batch_id: string;
  state: "running" | "completed" | "failed" | "cancelled" | "interrupted";
  request: BatchRequest;
  items: BatchItemSnapshot[];
  created_at: number;
  updated_at: number;
  error: string;
  log_path: string;
  status_path: string;
}

export interface KnowledgeEntrySummary {
  id: string;
  qualified_name: string;
  key: string;
  category: string;
  entry_type: string;
  intro: string;
  aliases: string[];
  visibility: "local" | "shareable" | string;
  maturity: "normal" | "tentative" | string;
  valid_from_rev: number;
  canonical_id: string;
  item_count: number;
}

export interface KnowledgeRevisionSummary {
  rev: number;
  created_at: string;
  kind: string;
  task_id: string;
  note: string;
}

export interface KnowledgeCandidate {
  candidate_key: string;
  task_id?: string;
  reason?: string;
  candidate?: string;
  missing?: string;
  freshness?: string;
  [key: string]: unknown;
}

export interface KnowledgeConflict {
  conflict_id: string;
  remote?: string;
  status: string;
  description: string;
  [key: string]: unknown;
}

export interface KnowledgePushRecord {
  remote?: string;
  queue_id?: number;
  status?: string;
  bundle_digest?: string;
  [key: string]: unknown;
}

export interface KnowledgeSnapshot {
  root: string;
  revision: number;
  version: string;
  entries: KnowledgeEntrySummary[];
  revisions: KnowledgeRevisionSummary[];
  pending_candidates: KnowledgeCandidate[];
  conflicts: KnowledgeConflict[];
  registered_remotes: string[];
  pushes: KnowledgePushRecord[];
}

export interface KnowledgeEntryDocument {
  id: string;
  qualified_name: string;
  key: string;
  category: string;
  revision: number;
  valid_from_rev: number;
  text: string;
}

export type KnowledgeMaintenanceCommand =
  | "log"
  | "show"
  | "edit"
  | "new"
  | "retire"
  | "revert"
  | "restore"
  | "refresh"
  | "phase-b"
  | "candidates"
  | "verify"
  | "repair"
  | "ingest";

export type KnowledgeShareCommand =
  | "register"
  | "mark"
  | "unmark"
  | "push"
  | "status"
  | "pull"
  | "conflicts"
  | "review";

export interface KnowledgeCommandResult {
  command: string;
  exit_code: number;
  output: string;
}

export interface KnowledgeFeedbackHint {
  category: string;
  entry: string;
  sub?: string;
  direction?: string;
  focus?: string;
  reason?: string;
  source_ids?: string[];
  confidence?: number;
}

export interface KnowledgeFeedbackSlice {
  chunk_id?: string;
  hints: KnowledgeFeedbackHint[];
  asr_corrections: string[];
  uncertainties: string[];
  warnings: string[];
  retrieval_urls: string[];
}

export interface KnowledgeFeedback {
  artifact_dir: string;
  windows: KnowledgeFeedbackSlice[];
  research: KnowledgeFeedbackSlice | null;
  merged_hints: KnowledgeFeedbackHint[];
  asr_corrections: string[];
  uncertainties: string[];
  warnings: string[];
}

export interface RefinedKnowledgeUpdateRequest {
  task_id: string;
  refined_srt: string;
  task_summary?: string;
  llm_model?: string[];
  apply?: boolean;
  resume?: boolean;
}

export interface RefinedKnowledgeUpdateReport {
  mode?: string;
  task_fingerprint?: string;
  chunks?: unknown[];
  warnings?: string[];
  ledger_path?: string;
  skipped?: string;
  output?: string;
  [key: string]: unknown;
}

export interface DiagnosticsReport {
  healthy: boolean;
  app_version: string;
  core_version: string;
  resources: ResourceStatus[];
  blocking_resources: string[];
  python_executable: string;
  disk_free_bytes: number | null;
  paths: Record<string, string>;
  capabilities: CapabilityState;
  gpu: GpuSnapshot;
  active_task: JobSnapshot | null;
  active_batch?: BatchSnapshot | null;
}

export interface StorageState {
  big_data: string;
  default_big_data: string;
  runtime: string;
  models: string;
  cache: string;
  tasks: string;
  agent_capsules: string;
  relocated: boolean;
}

export interface StorageMaintenanceResult {
  cancelled: boolean;
  storage: StorageState;
  resources?: ResourceStatus[];
  message?: string;
}

export interface KeyExportResult {
  cancelled: boolean;
  path: string | null;
  count: number;
}

/**
 * A sparse update to the remembered task options: null clears one back to the
 * code default rather than writing the default out.
 */
export type TaskDefaultsPatch = {
  [K in keyof TaskRequest]?: TaskRequest[K] | null;
};

/** Settings this app remembers for itself (user-data/settings.json). */
export interface Preferences {
  /** Renderer-only state: theme, language, dismissed dialogs. */
  ui: Record<string, unknown>;
  /** What the task form starts with. Absent field = follow the code default. */
  task_defaults: Partial<TaskRequest>;
}

/**
 * The slice of config.toml the settings panel can write. Shared with the CLI
 * and hand-editable, so null means "not set" (the key is removed) rather than
 * "write the default".
 */
export interface SharedSettings {
  split_length_scale: number | null;
}

export interface BootstrapState {
  app_version: string;
  resources: ResourceStatus[];
  resource_installs: ResourceInstallSnapshot[];
  capabilities: CapabilityState;
  settings: PublicSettings;
  routing?: RoutingSettings;
  preferences: Preferences;
  shared_settings: SharedSettings;
  /** Shown in the panel: the file is meant to be editable by hand. */
  config_path: string;
  storage?: StorageState;
  gpus?: GpuSnapshot;
  task: JobSnapshot | null;
  tasks?: JobSnapshot[];
  batch?: BatchSnapshot | null;
  batches?: BatchSnapshot[];
}

export interface PollResult {
  events: WorkerEvent[];
  nextCursor: number;
}

export interface UpdateCheck {
  available: boolean;
  version: string;
  kind?: "app" | "full";
  releaseNotes?: string;
  mandatory?: boolean;
  size?: number;
  releaseUrl?: string;
}

export interface UpdateInstallSnapshot {
  version: string;
  kind: "app" | "full";
  state: "queued" | "running" | "ready" | "failed";
  phase: "waiting" | "downloading" | "installing" | "complete";
  message: string;
  downloaded: number;
  total: number;
  bytes_per_second: number;
  /** An app delta only swaps the version pointer: relaunch and it is live. */
  restart_required: boolean;
  /** A full package hands off to an external updater that replaces this
   *  install, so FineSub has to quit before it can proceed. */
  exit_required: boolean;
  error: string;
  started_at: number;
  updated_at: number;
}

export interface DesktopApi {
  getBootstrapState(): Promise<BootstrapState>;
  getDiagnostics(): Promise<DiagnosticsReport>;
  selectInputFile(): Promise<{ path: string | null }>;
  selectBatchFiles(): Promise<{ paths: string[] }>;
  startTask(request: Partial<TaskRequest> & { input: string }): Promise<JobSnapshot>;
  cancelTask(taskId: string): Promise<JobSnapshot>;
  retryTask(taskId: string): Promise<JobSnapshot>;
  resumeTask(taskId: string): Promise<JobSnapshot>;
  deleteTaskIntermediates(taskId: string): Promise<JobSnapshot>;
  getTaskSnapshot(): Promise<JobSnapshot | null>;
  listTasks(): Promise<JobSnapshot[]>;
  pollEvents(cursor: number): Promise<PollResult>;
  startBatch(request: BatchRequest): Promise<BatchSnapshot>;
  cancelBatch(batchId: string): Promise<BatchSnapshot>;
  resumeBatch(batchId: string): Promise<BatchSnapshot>;
  getBatchSnapshot(): Promise<BatchSnapshot | null>;
  listBatches(): Promise<BatchSnapshot[]>;
  openBatchDirectory(batchId: string): Promise<{ path: string }>;
  openBatchOutput(batchId: string, path: string): Promise<{ path: string }>;
  openBatchLog(batchId: string): Promise<{ path: string }>;
  installResource(resourceId: string): Promise<ResourceInstallSnapshot>;
  getResourceInstall(resourceId: string): Promise<ResourceInstallSnapshot | null>;
  listResourceInstalls(): Promise<ResourceInstallSnapshot[]>;
  pauseResourceInstall(resourceId: string): Promise<ResourceInstallSnapshot>;
  openInstallLogs(): Promise<unknown>;
  rescanGpus(): Promise<unknown>;
  openResourceLocation(
    resourceId: string,
    kind: "cache" | "install",
  ): Promise<{ path: string }>;
  saveApiKeys(keys: {
    gemini_free?: string | null;
    gemini_paid?: string | null;
    exa?: string | null;
    tavily?: string | null;
  }): Promise<PublicSettings>;
  deleteApiKey(provider: ApiProvider): Promise<PublicSettings>;
  revealApiKeys(): Promise<RevealedApiKeys>;
  exportApiKeys(): Promise<KeyExportResult>;
  getRoutingSettings(): Promise<RoutingSettings>;
  saveRoutingSettings(values: RoutingUpdate): Promise<RoutingSettings>;
  saveProviderKey(providerId: string, value: string): Promise<RoutingSettings>;
  deleteProviderKey(providerId: string): Promise<RoutingSettings>;
  probeLocalAgents(): Promise<LocalAgentStatus[]>;
  getKnowledgeSnapshot(): Promise<KnowledgeSnapshot>;
  getKnowledgeEntry(name: string, rev?: number | null): Promise<KnowledgeEntryDocument>;
  runKnowledgeMaintenance(request: {
    command: KnowledgeMaintenanceCommand;
    args?: string[];
    content?: string;
  }): Promise<KnowledgeCommandResult>;
  runKnowledgeShare(request: {
    command: KnowledgeShareCommand;
    args?: string[];
  }): Promise<KnowledgeCommandResult>;
  getTaskKnowledgeFeedback(taskId: string): Promise<KnowledgeFeedback>;
  runRefinedKnowledgeUpdate(
    request: RefinedKnowledgeUpdateRequest,
  ): Promise<RefinedKnowledgeUpdateReport>;
  openKnowledgeDirectory(): Promise<{ path: string }>;
  relocateData(reset?: boolean): Promise<StorageMaintenanceResult>;
  purgeRebuildableData(confirmation: string): Promise<StorageMaintenanceResult>;
  getPreferences(): Promise<{
    preferences: Preferences;
    shared: SharedSettings;
    config_path: string;
  }>;
  savePreferences(patch: {
    ui?: Record<string, unknown> | null;
    task_defaults?: TaskDefaultsPatch | null;
  }): Promise<{ preferences: Preferences }>;
  saveSharedSettings(
    values: SharedSettings,
  ): Promise<{ shared: SharedSettings; config_path: string }>;
  checkUpdates(): Promise<UpdateCheck>;
  installUpdate(kind: "app" | "full", version: string): Promise<UpdateInstallSnapshot>;
  getUpdateInstall(): Promise<UpdateInstallSnapshot | null>;
  openUpdatePage(): Promise<{ url: string }>;
  openTasksDirectory(taskId?: string): Promise<{ path: string }>;
  openOutput(path: string): Promise<{ path: string }>;
  minimizeWindow(): Promise<unknown>;
  minimizeToTray(): Promise<unknown>;
  maximizeWindow(): Promise<unknown>;
  closeWindow(): Promise<unknown>;
  setWindowChrome(background: string, foreground: string): Promise<unknown>;
}
