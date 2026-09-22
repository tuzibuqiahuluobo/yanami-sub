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
