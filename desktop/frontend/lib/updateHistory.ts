import type { Language } from "./translations";


export interface UpdateHistoryEntry {
  version: string;
  title: Record<Language, string>;
  notes: Record<Language, readonly string[]>;
}


/**
 * Concise, bundled history for the update announcement.
 *
 * The available release's complete notes come from the signed update
 * manifest. Older notes stay in the application so opening history never
 * adds another GitHub request to an already network-sensitive workflow.
 */
export const UPDATE_HISTORY: readonly UpdateHistoryEntry[] = [
  {
    version: "0.1.0-rc.6.post3",
    title: { zh: "RC6.3 · 依赖安装恢复", en: "RC6.3 · Dependency installation recovery" },
    notes: {
      zh: [
        "延长依赖下载的超时和重试，并在失败时提供准确的依赖链接与日志。",
        "支持从缓存复用手动下载且通过 SHA-256 校验的 wheel。",
        "整理资源目录按钮及应用更新操作的布局。",
      ],
      en: [
        "Extended dependency download timeouts and retries with exact failure links and logs.",
        "Allowed verified, manually downloaded wheels to be reused from the cache.",
        "Refined resource folder controls and update action placement.",
      ],
    },
  },
  {
    version: "0.1.0-rc.6.post2",
    title: { zh: "RC6.2 · 下载线路切换", en: "RC6.2 · Download route selection" },
    notes: {
      zh: [
        "资源页可查看并切换自动、国内镜像与官方源下载线路。",
        "重新选择自动时立即探测网络，失败后可切换线路重试。",
      ],
      en: [
        "Added visible automatic, mainland-mirror, and official-source download routes.",
        "Re-probed the network when reselecting automatic and allowed route switching after failures.",
      ],
    },
  },
  {
    version: "0.1.0-rc.6.post1",
    title: { zh: "RC6.1 · 更新恢复与模型可用性", en: "RC6.1 · Update recovery and model availability" },
    notes: {
      zh: [
        "完整更新增加进度标记、完整性核验、自动回退和可靠的失败回滚。",
        "增强本地 Agent 检测，并让检测结果真正进入单任务、批处理和知识库流程。",
        "补充 API 密钥获取教程，保存后立即刷新模型可用状态。",
      ],
      en: [
        "Added update markers, integrity checks, automatic fallback, and reliable rollback.",
        "Expanded local Agent discovery and connected detected commands to every task flow.",
        "Added API-key guides and immediate model-availability refresh after saving credentials.",
      ],
    },
  },
  {
    version: "0.1.0-rc.6",
    title: { zh: "RC6 · 界面反馈与更新进度", en: "RC6 · Interface feedback and update progress" },
    notes: {
      zh: [
        "统一主题色焦点样式，并为完成操作增加右下角成功提示。",
        "把应用更新下载改为跨页面保留的圆形进度提示。",
        "让页签文字平滑淡入淡出，并统一受界面动画设置控制。",
      ],
      en: [
        "Unified themed focus styles and added bottom-right success notifications.",
        "Moved update downloads into a circular progress indicator that survives page changes.",
        "Smoothed tab-label transitions under the shared interface-motion preference.",
      ],
    },
  },
  {
    version: "0.1.0-rc.5.post4",
    title: { zh: "RC5.4 · Python 准备与更新公告", en: "RC5.4 · Python setup and update announcements" },
    notes: {
      zh: [
        "将 Python 发现改为有进度、有超时且可跳过的准备流程，并支持即时指定解释器。",
        "规避私有 Python 安装中的 Windows 装入点错误，同时保持依赖环境隔离。",
        "新增可关闭的启动更新公告，并按需加载历史更新内容。",
      ],
      en: [
        "Made Python discovery bounded, visible, skippable, and immediately configurable.",
        "Avoided the Windows mount-point failure while keeping managed dependencies isolated.",
        "Added dismissible update announcements with on-demand release history.",
      ],
    },
  },
  {
    version: "0.1.0-rc.5.post3",
    title: { zh: "RC5.3 · 运行环境与任务流程修复", en: "RC5.3 · Runtime and task-flow fixes" },
    notes: {
      zh: [
        "补齐 PATH、py 启动器和常见目录中的 Python 3.12 发现，并允许手动指定解释器。",
        "修复弹窗随滚动容器偏移、诊断状态误判和模型实际目录显示不准。",
        "新增翻译字幕输出档位，并修复任务完成后无法从侧栏新建任务。",
      ],
      en: [
        "Expanded Python 3.12 discovery and added manual interpreter selection.",
        "Fixed off-screen dialogs, diagnostic severity, and effective model paths.",
        "Added translated-subtitle output and restored New Task after completion.",
      ],
    },
  },
  {
    version: "0.1.0-rc.5.post2",
    title: { zh: "RC5.2 · 界面交互统一", en: "RC5.2 · Consistent interface interactions" },
    notes: {
      zh: [
        "统一输入框、下拉菜单和知识库表单的圆角及交互状态。",
        "为任务、批处理、知识库和主题切换加入可关闭的主题色过渡。",
        "恢复在线更新清单，并遵循系统的减少动态效果设置。",
      ],
      en: [
        "Unified rounded inputs, menus, and knowledge forms.",
        "Added theme-coloured transitions controlled by the interface-motion switch.",
        "Restored online manifests and respected reduced-motion preferences.",
      ],
    },
  },
  {
    version: "0.1.0-rc.5.post1",
    title: { zh: "RC5.1 · 更新网络容错", en: "RC5.1 · Resilient update networking" },
    notes: {
      zh: [
        "代理返回限流、认证失败或临时错误时自动尝试其他线路和直连。",
        "更新检查失败时给出切换网络或暂时关闭代理的建议，并写入会话日志。",
      ],
      en: [
        "Retried update checks over alternate routes and direct access after proxy failures.",
        "Added actionable network guidance and session-log diagnostics.",
      ],
    },
  },
  {
    version: "0.1.0-rc.5",
    title: { zh: "RC5 · 更新、卸载与首次启动修复", en: "RC5 · Update, uninstall, and first-run fixes" },
    notes: {
      zh: [
        "修复立即重启、卸载时关闭进程、首次安装浅色主题和知识库假加载状态。",
        "完整更新器开始保留 Windows 卸载器，为后续应用内更新恢复安全基础。",
      ],
      en: [
        "Fixed restart-now, process shutdown on uninstall, the light first-run theme, and stale knowledge loading.",
        "Full updates began preserving the Windows uninstaller for safe future in-app updates.",
      ],
    },
  },
  {
    version: "0.1.0-rc.4",
    title: { zh: "RC4 · 状态与错误反馈", en: "RC4 · State and error feedback" },
    notes: {
      zh: [
        "增加任务启动前的联网检索与模型路由校验。",
        "任务历史和资源状态自动刷新，界面显示简洁错误并保留完整日志。",
        "新安装默认使用 Yanami Sub 产品目录。",
      ],
      en: [
        "Validated research and model routing before a task starts.",
        "Refreshed task and resource state live while keeping full errors in logs.",
        "New installs adopted the Yanami Sub product directory.",
      ],
    },
  },
  {
    version: "0.1.0-rc.3",
    title: { zh: "RC3 · Yanami Sub 迁移预览", en: "RC3 · Yanami Sub migration preview" },
    notes: {
      zh: [
        "项目、可执行文件、安装器和更新资产统一改名为 Yanami Sub。",
        "固定 FineSub v0.5.1，加入中文安装器、多资源并行下载、本地复用和 TUNA 镜像。",
        "完善批处理、路由、知识库、诊断和中文使用文档。",
      ],
      en: [
        "Renamed the product, executable, installer, and update assets to Yanami Sub.",
        "Pinned FineSub v0.5.1 and added parallel downloads, local reuse, and the TUNA mirror.",
        "Expanded batch, routing, knowledge, diagnostics, and Chinese documentation.",
      ],
    },
  },
] as const;


export function updateHistoryFor(language: Language): Array<{
  version: string;
  title: string;
  notes: readonly string[];
}> {
  return UPDATE_HISTORY.map((entry) => ({
    version: entry.version,
    title: entry.title[language],
    notes: entry.notes[language],
  }));
}
