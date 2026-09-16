import type {
  ApiEnvelope,
  BatchRequest,
  BatchSnapshot,
  BootstrapState,
  CapabilityState,
  DiagnosticsReport,
  DesktopApi,
  JobSnapshot,
  KnowledgeEntryDocument,
  KnowledgeFeedback,
  KnowledgeSnapshot,
  Preferences,
  PublicSettings,
  PythonInterpreterChoice,
  ResourceInstallSnapshot,
  ResourceStatus,
  RevealedApiKeys,
  TaskRequest,
  UpdateInstallSnapshot,
} from "./types";


type BridgeMethod = (...args: unknown[]) => Promise<ApiEnvelope<unknown>>;
type NativeBridge = Record<string, BridgeMethod>;

declare global {
  interface Window {
    pywebview?: {
      api?: NativeBridge;
    };
  }
}


export class BridgeCallError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly action?: string | null,
  ) {
    super(message);
    this.name = "BridgeCallError";
  }
}


export function unwrapEnvelope<T>(envelope: ApiEnvelope<T>): T {
  if (envelope.ok) {
    return envelope.data;
  }
  throw new BridgeCallError(
    envelope.error.code,
    envelope.error.message,
    envelope.error.action,
  );
}


const previewBootstrap: BootstrapState = {
  app_version: "development",
  // The same resources the backend reports, with optional rows left
  // uninstalled so the preview also shows their on-demand presentation.
  resources: [
    { id: "uv", version: "0.11.32", state: "ready" },
    { id: "ffmpeg", version: "N-125752", state: "ready" },
    { id: "git", version: "2.55.0.3", state: "ready" },
    // Deliberately one version behind, so the browser preview also shows the
    // "installed but not the newest" row -- the state that must not gate a task.
    {
      id: "yt-dlp",
      version: "2026.07.20",
      installed_version: "2026.05.02",
      state: "outdated",
    },
    {
      id: "tokcount",
      version: "1.62.0-0",
      state: "missing",
      optional: true,
    },
    {
      id: "models",
      version: "on-demand",
      state: "missing",
      detail: "还需下载 3/3 个模型",
      optional: true,
    },
  ],
  resource_installs: [],
  capabilities: {
    raw_srt: true,
    translation: false,
    web_search: false,
  },
  settings: {
    api_keys: {
      gemini_free: "missing",
      gemini_paid: "missing",
      exa: "missing",
      tavily: "missing",
    },
  },
  routing: {
    active_preset_id: "default",
    execution_policy: "agent-text-preferred",
    local_agent_timeout_seconds: 1680,
    local_agent_allow_unisolated_user_config: false,
    local_agent_service_tier: "",
    local_agent_reasoning_effort: "",
    local_agent_max_parallel: 4,
    presets: [
      { id: "default", name: "默认", active: true, test_target_id: "gemini-free-3_5-flash-lite", uses_local_agent: false, warnings: [] },
      { id: "agy-hybrid", name: "agy 混合", active: false, test_target_id: "gemini-free-3_5-flash-lite", uses_local_agent: true, warnings: [] },
      { id: "agy", name: "agy 独占", active: false, test_target_id: "local-agy-media-gemini-3_7-flash", uses_local_agent: true, warnings: [] },
    ],
    policies: ["agent-text-preferred", "api-only", "agent-only"],
    providers: [
      { id: "GEMINI_FREE", kind: "gemini", base_url: "", key_env: "", configured: false },
      { id: "GEMINI_PAID", kind: "gemini", base_url: "", key_env: "", configured: false },
      { id: "LOCAL_CODEX", kind: "local_agent", base_url: "", key_env: "", configured: false },
    ],
    targets: [
      { id: "gemini-free-3_5-flash-lite", display_name: "3.5 Flash Lite", backend: "gemini_rest", provider_tier: "GEMINI_FREE", api_model_id: "gemini/gemini-3.5-flash-lite", supports_audio: true, supports_video: true, supports_native_search: false, is_free: true, quality_score: 60 },
      { id: "local-codex-gpt-5_6", display_name: "GPT-5.6 via Codex", backend: "local_agent", provider_tier: "LOCAL_CODEX", api_model_id: "gpt-5.6", supports_audio: false, supports_video: false, supports_native_search: true, is_free: false, quality_score: 80 },
    ],
    model_groups: {
      "gemini-free-default": ["gemini-free-3_5-flash-lite"],
      "codex-default": ["local-codex-gpt-5_6"],
    },
    task_groups: ["correction-mm", "correction-text", "planning-mm", "planning-text", "research", "search_judge", "knowledge"],
    local_agent_bound: false,
    config_path: String.raw`C:\Users\preview\AppData\Local\FineSub\user-data\config.toml`,
    error: "",
  },
  preferences: { ui: {}, task_defaults: {} },
  shared_settings: { split_length_scale: null },
  config_path: String.raw`C:\Users\preview\AppData\Local\FineSub\user-data\config.toml`,
  storage: {
    big_data: String.raw`C:\Yanami Sub`,
    default_big_data: String.raw`C:\Yanami Sub`,
    runtime: String.raw`C:\Yanami Sub\runtime`,
    models: String.raw`C:\Yanami Sub\models`,
    cache: String.raw`C:\Yanami Sub\cache`,
    tasks: String.raw`C:\Yanami Sub\tasks`,
    agent_capsules: String.raw`C:\Yanami Sub\agent`,
    relocated: false,
  },
  task: null,
  batch: null,
  batches: [],
  // One finished recognition-only run for the file selectInputFile returns,
  // so the reuse suggestion and the history's continue button show up in the
  // browser preview.
  tasks: [
    {
      task_id: "示例视频-260806-2210-a1b2c3",
      state: "completed",
      created_at: 1754500000,
      events: [],
      request: {
        input: "D:/Media/示例视频.mp4",
        output: "C:/Yanami Sub/tasks/示例视频-260806-2210-a1b2c3/示例视频.srt",
        name: "",
        cleanup_intermediate: false,
        stage: "raw-srt",
        model_name: "large-v3-turbo",
        device: "cuda",
        language: null,
        gpu_tier: "auto",
        gap_sec: 0.3,
        qwen_verify: "auto",
        lang_redecode: "auto",
        asr_decode_batch: "auto",
        asr_context: "off",
        word: false,
        asr_stabilize_profile: 0,
        llm_media: "video",
        llm_correction_media: "",
        llm_planning_media: "",
        llm_retrieval: "local",
        llm_difficulty: "quality",
        llm_continuity: "serial",
        llm_parallel_windows: 1,
        llm_fast: "auto",
        llm_output_scale: 1,
        llm_model: [],
        download_video_source: true,
        extra_info: "",
        extra_style: "",
        knowledge: "update",
        postprocess_profile: 0,
        max_retries_per_window: 5,
        max_replacements_per_window: 1,
        resume: true,
      },
      outputs: { rawSrt: "D:/Media/示例视频-raw.srt" },
    },
  ],
};


function previewApi(): DesktopApi {
  let settings = structuredClone(previewBootstrap.settings);
  let routing = structuredClone(previewBootstrap.routing!);
  let preferences = structuredClone(previewBootstrap.preferences);
  let shared = structuredClone(previewBootstrap.shared_settings);
  let storage = structuredClone(previewBootstrap.storage!);
  const installs = new Map<string, ResourceInstallSnapshot>();
  let batch: BatchSnapshot | null = null;
  return {
    async getBootstrapState() {
      return structuredClone({
        ...previewBootstrap,
        settings,
        routing,
        preferences,
        shared_settings: shared,
        storage,
      });
    },
    async getDiagnostics() {
      return {
        healthy: true,
        app_version: previewBootstrap.app_version,
        core_version: "0.5.1",
        resources: structuredClone(previewBootstrap.resources),
        blocking_resources: [],
        python_executable: String.raw`C:\Yanami Sub\runtime\python\Scripts\python.exe`,
        disk_free_bytes: 80 * 1024 ** 3,
        paths: {
          install: String.raw`C:\Yanami Sub`,
          personal_data: String.raw`C:\Users\preview\AppData\Local\FineSub\user-data`,
          big_data: String.raw`C:\Yanami Sub`,
          models: String.raw`C:\Yanami Sub\models`,
          cache: String.raw`C:\Yanami Sub\cache`,
          tasks: String.raw`C:\Yanami Sub\tasks`,
          logs: String.raw`C:\Users\preview\AppData\Local\FineSub\user-data\logs`,
        },
        capabilities: structuredClone(previewBootstrap.capabilities),
        gpu: { state: "ready", devices: [] },
        active_task: null,
      };
    },
    async selectInputFile() {
      return { path: "D:/Media/示例视频.mp4" };
    },
    async selectBatchFiles() {
      return {
        paths: ["D:/Media/示例视频-1.mp4", "D:/Media/示例视频-2.mp4"],
      };
    },
    async importBatchManifest() {
      return {
        cancelled: false,
        path: "D:/Media/finesub-batch.jsonl",
        request: {
          items: [
            {
              input: "D:/Media/清单视频.mp4",
              ...requestDefaults,
              group: "",
              priority: 1,
            },
          ],
          workers: { download: 2, asr: 1, llm: 2 },
          asr_queue_size: 4,
          retry_failed: 1,
        },
        ignored_fields: [],
      };
    },
    async exportBatchManifest(request) {
      return {
        cancelled: false,
        path: "D:/Media/finesub-batch.jsonl",
        count: request.items.length,
      };
    },
    async startTask(request) {
      return {
        task_id: "preview-task",
        state: "running",
        request: {
          ...requestDefaults,
          ...request,
        } as TaskRequest,
        events: [],
        outputs: {},
      };
    },
    async cancelTask(taskId) {
      return {
        task_id: taskId,
        state: "cancelled",
        events: [],
        outputs: {},
      };
    },
    async retryTask(taskId) {
      return {
        task_id: `${taskId}-retry`,
        state: "running",
        request: { input: "D:/Media/示例视频.mp4", ...requestDefaults },
        events: [],
        outputs: {},
      };
    },
    async resumeTask(taskId) {
      return {
        task_id: taskId,
        state: "running",
        request: { input: "D:/Media/示例视频.mp4", ...requestDefaults },
        events: [],
        outputs: {},
      };
    },
    async deleteTaskIntermediates(taskId) {
      return {
        task_id: taskId,
        state: "completed",
        request: { input: "D:/Media/示例视频.mp4", ...requestDefaults },
        events: [],
        outputs: {},
      };
    },
    async getTaskSnapshot() {
      return null;
    },
    async listTasks() {
      return [];
    },
    async pollEvents(cursor) {
      return { events: [], nextCursor: cursor };
    },
    async startBatch(request: BatchRequest) {
      const now = Date.now() / 1000;
      batch = {
        batch_id: "batch-preview",
        state: "running",
        request: structuredClone(request),
        items: request.items.map((item, index) => ({
          index,
          input: item.input,
          label: item.input.split(/[\\/]/).pop() || item.input,
          state: index === 0 ? "running" : "queued",
          stage: index === 0 ? "asr" : "",
          error: "",
          outputs: {},
        })),
        created_at: now,
        updated_at: now,
        error: "",
        log_path: "C:/Yanami Sub/tasks/batches/batch-preview/batch-log.txt",
        status_path: "C:/Yanami Sub/tasks/batches/batch-preview/batch-status.jsonl",
      };
      return structuredClone(batch);
    },
    async cancelBatch() {
      if (!batch) throw new BridgeCallError("batch_not_found", "没有找到该批次。");
      batch = { ...batch, state: "cancelled", updated_at: Date.now() / 1000 };
      return structuredClone(batch);
    },
    async resumeBatch() {
      if (!batch) throw new BridgeCallError("batch_not_found", "没有找到该批次。");
      batch = { ...batch, state: "running", updated_at: Date.now() / 1000 };
      return structuredClone(batch);
    },
    async getBatchSnapshot() {
      return structuredClone(batch);
    },
    async listBatches() {
      return batch ? [structuredClone(batch)] : [];
    },
    async openBatchDirectory() {
      return { path: "C:/Yanami Sub/tasks/batches/batch-preview" };
    },
    async openBatchOutput(_batchId, path) {
      return { path };
    },
    async openBatchLog() {
      return { path: "C:/Yanami Sub/tasks/batches/batch-preview/batch-log.txt" };
    },
    async installResource(resourceId) {
      const now = Date.now() / 1000;
      const snapshot: ResourceInstallSnapshot = {
        resource_id: resourceId,
        resource_version: "preview",
        state: "running",
        phase: "downloading",
        message: "正在下载资源",
        downloaded: 42_000_000,
        total: 100_000_000,
        bytes_per_second: 3_200_000,
        cache_path: "C:\\Yanami Sub\\cache\\downloads",
        install_path: `C:\\Yanami Sub\\runtime\\${resourceId}`,
        logs: [],
        error: "",
        started_at: now,
        updated_at: now,
      };
      installs.set(resourceId, snapshot);
      return structuredClone(snapshot);
    },
    async getResourceInstall(resourceId) {
      return structuredClone(installs.get(resourceId) ?? null);
    },
    async listResourceInstalls() {
      return structuredClone([...installs.values()]);
    },
    async getResourceStatuses() {
      return structuredClone(previewBootstrap.resources);
    },
    async pauseResourceInstall(resourceId) {
      const current = installs.get(resourceId);
      if (!current) {
        throw new BridgeCallError("not_found", "没有找到资源下载任务。");
      }
      const paused = {
        ...current,
        state: "paused" as const,
        message: "已暂停，已下载内容会保留",
      };
      installs.set(resourceId, paused);
      return structuredClone(paused);
    },
    async openResourceLocation(resourceId, kind) {
      return {
        path:
          kind === "cache"
            ? "C:\\Yanami Sub\\cache\\downloads"
            : `C:\\Yanami Sub\\runtime\\${resourceId}`,
      };
    },
    async openInstallLogs() {
      return { path: "C:\\Users\\me\\AppData\\Local\\FineSub\\user-data\\logs" };
    },
    async getPythonInterpreter() {
      return {
        configured: null,
        found: "C:\\Python312\\python.exe",
        version: "3.12.6",
        detail: "",
        rejected: [],
      };
    },
    async selectPythonInterpreter() {
      return { cancelled: true };
    },
    async setPythonInterpreter(path: string) {
      return { path, version: "3.12.6", restart_required: true };
    },
    async clearPythonInterpreter() {
      return { restart_required: true };
    },
    async rescanGpus() {
      return { state: "ready", devices: [] };
    },
    async getPreferences() {
      return structuredClone({
        preferences,
        shared,
        config_path: previewBootstrap.config_path,
      });
    },
    async savePreferences(patch) {
      // Mirrors the store: only the sections present change, and a null value
      // resets that one setting instead of writing a default.
      const merge = (
        current: Record<string, unknown>,
        update: Record<string, unknown> | null | undefined,
      ) => {
        if (!update) return current;
        const next = { ...current };
        for (const [key, value] of Object.entries(update)) {
          if (value === null || value === undefined) delete next[key];
          else next[key] = value;
        }
        return next;
      };
      preferences = {
        ui: merge(preferences.ui, patch.ui),
        task_defaults: merge(
          preferences.task_defaults as Record<string, unknown>,
          patch.task_defaults as Record<string, unknown> | null | undefined,
        ) as Preferences["task_defaults"],
      };
      return structuredClone({ preferences });
    },
    async saveSharedSettings(values) {
      shared = structuredClone(values);
      return structuredClone({
        shared,
        config_path: previewBootstrap.config_path,
      });
    },
    async saveApiKeys(keys) {
      settings = {
        api_keys: {
          gemini_free: keys.gemini_free?.trim() ? "configured" : settings.api_keys.gemini_free,
          gemini_paid: keys.gemini_paid?.trim() ? "configured" : settings.api_keys.gemini_paid,
          exa: keys.exa?.trim() ? "configured" : settings.api_keys.exa,
          tavily: keys.tavily?.trim() ? "configured" : settings.api_keys.tavily,
        },
      };
      return structuredClone(settings);
    },
    async reloadSettings() {
      // The preview has no file behind it, so "re-read from disk" is the state
      // it already holds.
      return {
        settings: structuredClone(settings),
        capabilities: structuredClone(previewBootstrap.capabilities),
      };
    },
    async deleteApiKey(provider) {
      settings = {
        api_keys: { ...settings.api_keys, [provider]: "missing" },
      };
      return structuredClone(settings);
    },
    async revealApiKeys() {
      const fake = (
        provider: "gemini_free" | "gemini_paid" | "exa" | "tavily",
      ): RevealedApiKeys["gemini_free"] =>
        settings.api_keys[provider] === "configured"
          ? [
              {
                name: "main",
                key: `preview-${provider}-key-0000`,
                masked: "prev…0000",
              },
            ]
          : [];
      return {
        gemini_free: fake("gemini_free"),
        gemini_paid: fake("gemini_paid"),
        exa: fake("exa"),
        tavily: fake("tavily"),
      };
    },
    async exportApiKeys() {
      const count = Object.values(settings.api_keys).filter(
        (status) => status === "configured",
      ).length;
      return {
        cancelled: false,
        path: count ? "C:/Users/preview/Documents/finesub-api-keys.env" : null,
        count,
      };
    },
    async getRoutingSettings() {
      return structuredClone(routing);
    },
    async saveRoutingSettings(values) {
      routing = {
        ...routing,
        active_preset_id: values.preset,
        execution_policy: values.execution_policy,
        local_agent_timeout_seconds: values.local_agent_timeout_seconds,
        local_agent_allow_unisolated_user_config: values.local_agent_allow_unisolated_user_config,
        local_agent_service_tier: values.local_agent_service_tier,
        local_agent_reasoning_effort: values.local_agent_reasoning_effort,
        local_agent_max_parallel: values.local_agent_max_parallel,
        presets: routing.presets.map((preset) => ({
          ...preset,
          active: preset.id === values.preset,
        })),
      };
      return structuredClone(routing);
    },
    async saveProviderKey(providerId, _value) {
      routing.providers = routing.providers.map((provider) =>
        provider.id === providerId ? { ...provider, configured: true } : provider,
      );
      return structuredClone(routing);
    },
    async deleteProviderKey(providerId) {
      routing.providers = routing.providers.map((provider) =>
        provider.id === providerId ? { ...provider, configured: false } : provider,
      );
      return structuredClone(routing);
    },
    async probeLocalAgents() {
      return [
        { provider_tier: "LOCAL_CODEX", driver: "codex", models: ["gpt-5.6"], quota_pools: ["LOCAL_CODEX"], status: "ready" as const, available: true, version: "codex-cli preview", detail: "" },
        { provider_tier: "LOCAL_AGY", driver: "agy", models: ["gemini-3.7-flash"], quota_pools: ["AGY_GEMINI"], status: "missing" as const, available: false, version: "", detail: "agy is not installed" },
      ];
    },
    async relocateData(reset = false) {
      const root = reset
        ? storage.default_big_data
        : String.raw`D:\Yanami Sub Data`;
      storage = {
        ...storage,
        big_data: root,
        models: `${root}\\models`,
        cache: `${root}\\cache`,
        tasks: `${root}\\tasks`,
        agent_capsules: `${root}\\agent`,
        relocated: root !== storage.default_big_data,
      };
      return { cancelled: false, storage: structuredClone(storage), message: "moved" };
    },
    async purgeRebuildableData(confirmation) {
      if (confirmation !== "PURGE_REBUILDABLE_DATA") {
        throw new BridgeCallError("confirmation_required", "需要确认后才能清理。");
      }
      return {
        cancelled: false,
        storage: structuredClone(storage),
        resources: previewBootstrap.resources.map((resource) => ({
          ...resource,
          state: "missing" as const,
        })),
        message: "removed",
      };
    },
    async getKnowledgeSnapshot(): Promise<KnowledgeSnapshot> {
      return {
        root: String.raw`C:\Users\preview\AppData\Local\FineSub\user-data\knowledge`,
        revision: 12,
        version: "rev:12",
        entries: [
          {
            id: "subject-preview",
            qualified_name: "common/FineSub",
            key: "FineSub",
            category: "common",
            entry_type: "其他",
            intro: "字幕处理项目",
            aliases: ["Yanami Sub"],
            visibility: "local",
            maturity: "normal",
            valid_from_rev: 3,
            canonical_id: "",
            item_count: 4,
          },
        ],
        revisions: [
          {
            rev: 12,
            created_at: new Date().toISOString(),
            kind: "user",
            task_id: "preview-task",
            note: "browser preview",
          },
        ],
        pending_candidates: [],
        conflicts: [],
        registered_remotes: [],
        pushes: [],
      };
    },
    async getKnowledgeEntry(name, rev): Promise<KnowledgeEntryDocument> {
      return {
        id: "subject-preview",
        qualified_name: name || "common/FineSub",
        key: "FineSub",
        category: "common",
        revision: rev ?? 12,
        valid_from_rev: 3,
        text: "# FineSub\n\n字幕处理项目\n\n## 术语\n\n- Yanami Sub",
      };
    },
    async runKnowledgeMaintenance(request) {
      return {
        command: request.command,
        exit_code: 0,
        output: `preview: ${request.command} completed`,
      };
    },
    async runKnowledgeShare(request) {
      return {
        command: request.command,
        exit_code: 0,
        output: `preview: share ${request.command} completed`,
      };
    },
    async getTaskKnowledgeFeedback(): Promise<KnowledgeFeedback> {
      return {
        artifact_dir: String.raw`C:\Yanami Sub\tasks\preview.llm-artifacts`,
        windows: [],
        research: null,
        merged_hints: [
          {
            category: "common",
            entry: "FineSub",
            direction: "append_lines",
            focus: "产品名称",
          },
        ],
        asr_corrections: ["Fine Sub → FineSub"],
        uncertainties: [],
        warnings: [],
      };
    },
    async runRefinedKnowledgeUpdate() {
      return {
        mode: "refined_aligned",
        chunks: [{ status: "applied" }],
        warnings: [],
      };
    },
    async openKnowledgeDirectory() {
      return {
        path: String.raw`C:\Users\preview\AppData\Local\FineSub\user-data\knowledge`,
      };
    },
    async checkUpdates() {
      // Reports a release so the browser preview can show what an available
      // update looks like: the sidebar dot, the notes and the install button
      // are otherwise unreachable without a real release feed.
      return {
        available: true,
        version: "0.9.9-preview",
        kind: "app" as const,
        size: 12_345_678,
        releaseNotes: "浏览器预览中的示例更新说明。",
      };
    },
    async installUpdate(kind, version) {
      throw new Error("Updates are not available in the browser preview");
    },
    async getUpdateInstall() {
      return null;
    },
    async openUpdatePage() {
      return { url: "https://github.com/tuzibuqiahuluobo/yanami-sub/releases" };
    },
    async openTasksDirectory() {
      return { path: "C:\\Yanami Sub\\tasks" };
    },
    async openOutput(path) {
      return { path };
    },
    async minimizeWindow() { },
    async minimizeToTray() { },
    async maximizeWindow() { },
    async closeWindow() { },
    async restartApplication() { },
    async setWindowChrome() { },
  };
}


const requestDefaults: Omit<TaskRequest, "input"> = {
  output: null,
  name: "",
  cleanup_intermediate: false,
  stage: "raw-srt",
  model_name: "large-v3-turbo",
  device: null,
  language: null,
  gpu_tier: "auto",
  gap_sec: 0.3,
  qwen_verify: "auto",
  lang_redecode: "auto",
  asr_decode_batch: "auto",
  asr_context: "off",
  word: false,
  asr_stabilize_profile: 0,
  llm_media: "video",
  llm_correction_media: "",
  llm_planning_media: "",
  llm_retrieval: "local",
  llm_difficulty: "quality",
  llm_continuity: "serial",
  llm_parallel_windows: 1,
  llm_fast: "auto",
  llm_output_scale: 1,
  llm_model: [],
  download_video_source: true,
  extra_info: "",
  extra_style: "",
  knowledge: "update",
  postprocess_profile: 0,
  max_retries_per_window: 5,
  max_replacements_per_window: 1,
  resume: true,
};


async function waitForNativeBridge(): Promise<NativeBridge> {
  if (typeof window === "undefined") {
    throw new BridgeCallError("bridge_unavailable", "桌面桥接不可用。");
  }
  if (window.pywebview?.api) {
    return window.pywebview.api;
  }
  await new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(
      () => reject(new BridgeCallError("bridge_timeout", "桌面桥接连接超时。")),
      10_000,
    );
    window.addEventListener(
      "pywebviewready",
      () => {
        window.clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
  });
  if (!window.pywebview?.api) {
    throw new BridgeCallError("bridge_unavailable", "桌面桥接不可用。");
  }
  return window.pywebview.api;
}


function nativeApi(): DesktopApi {
  const call = async <T>(method: string, ...args: unknown[]): Promise<T> => {
    const bridge = await waitForNativeBridge();
    const implementation = bridge[method];
    if (!implementation) {
      throw new BridgeCallError(
        "method_unavailable",
        `桌面桥接缺少方法：${method}`,
      );
    }
    return unwrapEnvelope((await implementation(...args)) as ApiEnvelope<T>);
  };
  return {
    getBootstrapState: () => call<BootstrapState>("get_bootstrap_state"),
    getDiagnostics: () => call<DiagnosticsReport>("get_diagnostics"),
    selectInputFile: () => call<{ path: string | null }>("select_input_file"),
    selectBatchFiles: () => call<{ paths: string[] }>("select_batch_files"),
    importBatchManifest: () => call("import_batch_manifest"),
    exportBatchManifest: (request) => call("export_batch_manifest", request),
    startTask: (request) => call<JobSnapshot>("start_task", request),
    cancelTask: (taskId) => call<JobSnapshot>("cancel_task", taskId),
    retryTask: (taskId) => call<JobSnapshot>("retry_task", taskId),
    resumeTask: (taskId) => call<JobSnapshot>("resume_task", taskId),
    deleteTaskIntermediates: (taskId) =>
      call<JobSnapshot>("delete_task_intermediates", taskId),
    getTaskSnapshot: () => call<JobSnapshot | null>("get_task_snapshot"),
    listTasks: () => call<JobSnapshot[]>("list_tasks"),
    pollEvents: (cursor) => call("poll_events", cursor),
    startBatch: (request) => call<BatchSnapshot>("start_batch", request),
    cancelBatch: (batchId) => call<BatchSnapshot>("cancel_batch", batchId),
    resumeBatch: (batchId) => call<BatchSnapshot>("resume_batch", batchId),
    getBatchSnapshot: () => call<BatchSnapshot | null>("get_batch_snapshot"),
    listBatches: () => call<BatchSnapshot[]>("list_batches"),
    openBatchDirectory: (batchId) =>
      call<{ path: string }>("open_batch_directory", batchId),
    openBatchOutput: (batchId, path) =>
      call<{ path: string }>("open_batch_output", batchId, path),
    openBatchLog: (batchId) =>
      call<{ path: string }>("open_batch_log", batchId),
    installResource: (resourceId) =>
      call<ResourceInstallSnapshot>("install_resource", resourceId),
    getResourceInstall: (resourceId) =>
      call<ResourceInstallSnapshot | null>("get_resource_install", resourceId),
    listResourceInstalls: () =>
      call<ResourceInstallSnapshot[]>("list_resource_installs"),
    getResourceStatuses: () => call<ResourceStatus[]>("get_resource_statuses"),
    pauseResourceInstall: (resourceId) =>
      call<ResourceInstallSnapshot>("pause_resource_install", resourceId),
    openResourceLocation: (resourceId, kind) =>
      call<{ path: string }>("open_resource_location", resourceId, kind),
    openInstallLogs: () => call<{ path: string }>("open_install_logs"),
    rescanGpus: () => call("rescan_gpus"),
    getPythonInterpreter: () =>
      call<PythonInterpreterChoice>("get_python_interpreter"),
    selectPythonInterpreter: () =>
      call<{
        cancelled?: boolean;
        path?: string;
        version?: string;
        restart_required?: boolean;
      }>("select_python_interpreter"),
    setPythonInterpreter: (path) =>
      call<{ path: string; version: string; restart_required: boolean }>(
        "set_python_interpreter",
        path,
      ),
    clearPythonInterpreter: () =>
      call<{ restart_required: boolean }>("clear_python_interpreter"),
    saveApiKeys: (keys) => call<PublicSettings>("save_api_keys", keys),
    reloadSettings: () =>
      call<{ settings: PublicSettings; capabilities: CapabilityState }>(
        "reload_settings",
      ),
    deleteApiKey: (provider) =>
      call<PublicSettings>("delete_api_key", provider),
    revealApiKeys: () => call<RevealedApiKeys>("reveal_api_keys"),
    exportApiKeys: () => call("export_api_keys"),
    getRoutingSettings: () => call("get_routing_settings"),
    saveRoutingSettings: (values) => call("save_routing_settings", values),
    saveProviderKey: (providerId, value) =>
      call("save_provider_key", providerId, value),
    deleteProviderKey: (providerId) =>
      call("delete_provider_key", providerId),
    probeLocalAgents: () => call("probe_local_agents"),
    getKnowledgeSnapshot: () => call("get_knowledge_snapshot"),
    getKnowledgeEntry: (name, rev = null) =>
      call("get_knowledge_entry", name, rev),
    runKnowledgeMaintenance: (request) =>
      call("run_knowledge_maintenance", request),
    runKnowledgeShare: (request) => call("run_knowledge_share", request),
    getTaskKnowledgeFeedback: (taskId) =>
      call("get_task_knowledge_feedback", taskId),
    runRefinedKnowledgeUpdate: (request) =>
      call("run_refined_knowledge_update", request),
    openKnowledgeDirectory: () => call("open_knowledge_directory"),
    relocateData: (reset = false) => call("relocate_data", reset),
    purgeRebuildableData: (confirmation) =>
      call("purge_rebuildable_data", confirmation),
    getPreferences: () => call("get_preferences"),
    savePreferences: (patch) => call("save_preferences", patch),
    saveSharedSettings: (values) => call("save_shared_settings", values),
    checkUpdates: () => call("check_updates"),
    installUpdate: (kind, version) =>
      call<UpdateInstallSnapshot>("install_update", kind, version),
    getUpdateInstall: () =>
      call<UpdateInstallSnapshot | null>("get_update_install"),
    openUpdatePage: () => call<{ url: string }>("open_update_page"),
    openTasksDirectory: (taskId = "") =>
      call<{ path: string }>("open_tasks_directory", taskId),
    openOutput: (path) => call<{ path: string }>("open_output", path),
    minimizeWindow: () => call("minimize_window"),
    minimizeToTray: () => call("minimize_to_tray"),
    maximizeWindow: () => call("maximize_window"),
    closeWindow: () => call("close_window"),
    restartApplication: () => call("restart_application"),
    setWindowChrome: (background, foreground) =>
      call("set_window_chrome", background, foreground),
  };
}


export function createDesktopApi(
  options: { preview?: boolean } = {},
): DesktopApi {
  const queryPreview =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("preview") === "1";
  const preview =
    options.preview ??
    (queryPreview || process.env.NEXT_PUBLIC_DESKTOP_PREVIEW === "1");
  return preview ? previewApi() : nativeApi();
}


export const desktopApi = createDesktopApi();
