# Yanami Sub 中文使用说明

本文面向 `v0.1.0-rc.5.post2`（RC5.2）。字幕处理由固定版本的
[FineSub v0.5.1](https://github.com/caca2331/finesub/tree/v0.5.1) 提供。

## 安装与迁移

1. 在 [Yanami Sub Releases](https://github.com/tuzibuqiahuluobo/yanami-sub/releases)
   下载 `Yanami-Sub-0.1.0-rc.5.post2-Setup.exe` 和对应的 `.sha256` 文件。
2. 在 PowerShell 中运行以下命令校验安装包：

   ```powershell
   Get-FileHash .\Yanami-Sub-0.1.0-rc.5.post2-Setup.exe -Algorithm SHA256
   ```

3. 将输出与 `.sha256` 文件中的值比较，完全一致后再运行安装器。
4. 如果电脑上装有 FineSub Desktop，请先从托盘菜单退出旧程序。RC5.2 会沿用原安装记录、
   覆盖旧版并清理旧名称的可执行文件与快捷方式。

Windows 可能显示 SmartScreen 提示。请只使用本仓库 Release 的安装包，
并在运行前校验 SHA-256，不要从第三方下载站获取。

## 首次启动

Yanami Sub 本身是轻量桌面壳。首次使用某项能力时，它会按需准备：

- 隔离的 Python 3.12 运行环境与 AI 依赖；
- FFmpeg；
- 人声分离、Whisper ASR 和可选二次校验模型；
- URL 输入所需的下载工具。

资源页会显示整体进度和最新日志。多个互不依赖的资源可以同时下载；开始下载前，程序会扫描
本机磁盘并用文件大小与 SHA-256 判断能否安全复用。名称相同但版本或哈希不符的文件不会被使用。

## 创建字幕任务

1. 在左侧选择“新建任务”。
2. 选择本地音频 / 视频，或粘贴受支持的媒体 URL。
3. 选择处理阶段：

   - `原始字幕`：运行人声分离、识别和字幕稳定化，不调用 LLM；
   - `成品字幕`：在原始字幕基础上继续纠错、翻译和后处理。

4. 选择源语言；不确定时可使用自动检测。
5. 成品字幕建议填写背景信息，例如主播、节目、游戏和关键专名。
6. 点击开始并在任务页查看阶段、用时和滚动日志。

本地输入完成后，只会把可交付的 `.srt` 发布到源媒体旁。识别音频、对齐数据、运行元数据等
内部文件保存在受管任务目录，不会散落到源目录。若同名字幕不是 Yanami Sub 创建的，程序会
使用安全的新名称，不会直接覆盖用户文件。

## 高级设置

“高级设置”用于覆盖 FineSub 核心参数。留空或选择“跟随核心设置”时使用核心默认值。

- 语音：识别模型、设备、GPU 档位、VAD、上下文、解码和二次校验；
- 翻译：媒体输入、检索、难度、连续性、并发、重试预算和模型路由；
- 风格与知识：背景信息、翻译风格、命名方式、知识库读取 / 收集 / 更新模式；
- 清理：完成后删除可重建的中间产物，不影响已发布字幕和个人知识。

不知道某个值时不要盲目修改。FineSub 的参数含义与建议范围见上游
[调参说明](https://github.com/caca2331/finesub/blob/v0.5.1/docs/manual/tuning.md) 和
[模型选择](https://github.com/caca2331/finesub/blob/v0.5.1/docs/manual/models.md)。

## 翻译、API 与本机 Agent

在“设置 → 翻译与联网能力”中配置 Gemini、Exa 或自定义服务商。API Key 只写入本机
`%LOCALAPPDATA%\FineSub\user-data\.env`，不会回传到界面或上传到本仓库。

也可以让 FineSub 使用已安装的 Codex CLI、Claude Code 或 Antigravity CLI 订阅额度。Agent
能力、媒体支持和路由限制以 FineSub 上游的
[本机 Agent 文档](https://github.com/caca2331/finesub/blob/v0.5.1/docs/manual/agent.md) 为准。

## 批处理

批处理页可以混合加入本地文件与 URL：

- 调整项目顺序和优先级；
- 分别设置下载、ASR 和 LLM 并发；
- 单项失败隔离，不中断其他任务；
- 取消、重试或从已有产物恢复；
- 导入 / 导出兼容 FineSub 的 JSONL manifest。

导入 manifest 前请确认其中的输入路径可信。Yanami Sub 会校验桌面扩展字段，但任务本身仍可能
访问 manifest 明确指定的本地媒体和 URL。

## 知识库

知识库页包含条目、任务反馈、维护和共享：

- 从已完成任务读取不确定项和人工精修字幕；
- 预览后写回术语、规则、风格和人物信息；
- 修订、回退、重建索引和处理候选冲突；
- 连接共享服务、贡献条目并执行维护者审核。

知识数据与 FineSub CLI 共用。执行写入、回退、合并或审核前应先使用预览，并保留重要知识库的
备份。上游知识格式见
[FineSub 知识库说明](https://github.com/caca2331/finesub/blob/v0.5.1/docs/manual/knowledge.md)。

## 数据目录

| 内容 | 默认位置 | 是否可重建 |
| --- | --- | --- |
| 设置、API Key、知识库、历史 | `%LOCALAPPDATA%\FineSub\user-data` | 否，请备份 |
| Python 与工具 | 安装目录下 `runtime` | 是 |
| 模型 | 安装目录下 `models` | 是，可重新下载 |
| 下载缓存 | 安装目录下 `cache` | 是 |
| 受管任务与 URL 输出 | 安装目录下 `tasks` | 字幕不可重建时请保留 |

设置页可以迁移大文件目录。迁移前不要手动终止程序，也不要同时运行另一个正在使用这些资源的
Yanami Sub 或 FineSub CLI 实例。

## 更新与卸载

RC3 起使用新的 Yanami Sub 更新清单名称，旧版 FineSub Desktop 不会把它误识别为可自动安装的
更新。因此从旧名称迁移必须手动运行 Yanami Sub 安装器。RC4 的完整更新器不会保留 Windows
卸载器，所以 RC4/RC5/RC5.1 到 RC5.2 仍需要手动运行 RC5.2 Setup 覆盖安装；RC5 起已修复
该保护逻辑，供后续版本安全恢复应用内更新。

卸载程序会自动删除可重建的运行环境、模型和缓存；删除成品字幕与共享的 FineSub 个人数据前
会分别询问。静默卸载不会代替用户确认删除这些不可重建内容。

## 常见问题

### 依赖或模型下载失败

打开任务日志与资源页，先重试失败资源。中国大陆网络会优先走 TUNA 的 Python 镜像；模型和
其他资源仍可能需要官方源。代理、杀毒软件和磁盘剩余空间都会影响下载。

### 提示缺少 Python 模块

不要在系统 Python 中逐个 `pip install`。在资源页运行诊断或重建运行环境，保证依赖来自与
当前 FineSub 核心版本匹配的锁文件。

### 媒体格式无法识别

确认文件真实可播放且扩展名与内容一致，然后检查 FFmpeg 状态。零字节、下载未完成或只有网页
占位内容的“视频文件”不能被识别。

### 窗口关闭后仍在运行

如果设置为“关闭主面板时最小化至托盘”，关闭按钮只隐藏窗口。通过系统托盘中的 Yanami Sub
菜单选择“退出”即可完全结束。

更多处理层故障请查阅 FineSub 上游
[故障排查](https://github.com/caca2331/finesub/blob/v0.5.1/docs/manual/troubleshooting.md)。
