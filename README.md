# Yanami Sub

基于 [FineSub](https://github.com/caca2331/finesub) 的 Windows 桌面字幕工作台，提供单任务、批处理、本地 Agent / API 路由、知识库、资源管理和应用内更新。

当前版本系列：**0.3.0 正式版 / 0.3.1 RC1.0 预览版**，固定使用 [FineSub v0.7.0](https://github.com/caca2331/finesub/releases/tag/v0.7.0)。桌面端与字幕核心独立发版；本仓库不复制或分叉核心实现。

## 安装与开始

1. 从 [Releases](https://github.com/tuzibuqiahuluobo/yanami-sub/releases) 下载对应版本的安装器。
2. 退出旧版后安装。已有安装可选择原目录覆盖安装，无需先卸载或清空模型、任务与知识库。
3. 首次使用时在资源页准备 Python 3.12、FFmpeg 等组件；可复用本机受支持的解释器，缺失的依赖与模型按需下载。
4. 在“新建任务”选择本地音视频或粘贴链接，确认识别引擎、输出阶段与模型来源后开始。
5. 只需原始字幕时无需 LLM 凭据；需要纠错翻译时配置 API 密钥，或安装、登录对应 Agent CLI。

URL 下载还需要 yt-dlp。首次准备运行环境、模型、URL 下载和在线模型需要可用网络。大文件目录可在应用中迁移；占用随引擎和模型增加，不建议只预留几 GB。

## 识别引擎怎么选

| 引擎 | 运行位置与用途 | 注意事项 |
| --- | --- | --- |
| Whisper（默认） | 本地分离、识别、稳定化 | 不把音频交给云端识别服务；GPU 推荐，部分计算可回退 CPU |
| 本地 MOSS | 本地一体转写与说话人标注 | NVIDIA RTX 30 系列或更新，至少 8 GB 显存；首用额外下载约 1.7 GB 模型并编译内核 |
| Gemini 3.5 Transcribe | 云端一体转写 | 使用 Gemini 免费 key，消耗服务方额度 |
| MOSS Pro | 云端一体转写 | 配置 MOSS_PRO；超免费额度使用余额须在本次任务中明确开启，默认关闭 |
| MAI-Transcribe-2 | 云端一体转写 | OpenRouter 或 Azure Speech 凭据，按服务商规则付费 |

**选择云端引擎并开始任务，会将音频上传给对应服务商。** 额度、价格和模型可用性以账号为准，不保证永久免费。云端原始回答缓存用于续跑，请勿随意删除。切换引擎不会覆盖已有识别产物；要重新识别请新建任务。

中文素材在核心 0.7.0 中通常只纠错和基础润色、不翻译；普通话识别会转为简体。具体语言判断和产物语义见 [上游中文素材说明](https://github.com/caca2331/finesub/blob/v0.7.0/docs/manual/chinese.md)。

## 纠错翻译与本地 Agent

- “自动”优先可用免费 API，没有时使用本地 Agent；也可明确指定 API、某个 Agent 或手动模型路由。
- 设置中每个 Agent 有独立配置入口，路径用文件选择器指定；Codex 有自己的服务档位设置。通用超时、并发与路由仍为公共设置。
- CLI 就绪只表示程序、版本和所需能力可用，**不代表已登录、有模型权限或有剩余额度**。
- CodeBuddy 使用独立 CLI，不复用旧 WorkBuddy 桌面凭据。自动尝试所有 Agent 不会擅自启用可能扣积分的 CodeBuddy 路由。
- 标准档适合多数任务；精细档可能增加裁判、校对与耗时；快速预设倾向纯文本。实际步骤取决于预设和显式选项。
- 切换任务预设保留知识库读写选择，不再通过“使用预设默认参数”复选框把更新模式覆盖为只读。
- 模型失败会给出认证、额度、限流、权限或网络等排查方向；不能确定时明确说明可能性。仅交付原始字幕时会标明纠错已跳过，不冒充完整成功。

本地 Agent 也可能向其供应商发送任务内容，并非离线模型；联网、音视频支持与计费取决于具体模型和账号。

## 批处理、知识库与日志

- 批处理复用单任务的处理设置，支持本地文件与链接、并发、重试、续跑和运行中追加。
- 知识库支持浏览、修订、任务反馈、双语字幕材料、预览提案后应用、维护及共享。双语文本可作为术语与润色证据，不等同于音频误听证据。
- “记住上次使用的设置”控制任务、批处理及知识库选项恢复；不记忆任务文件、正文、凭据或一次性的 MOSS 付费许可。
- 每个任务有带时间戳的日志；实际响应模型与候选顺序分开记录。设置底部可查看任务日志及应用日志位置。
- 本地媒体的交付字幕发布到源文件旁；内部产物留在受管目录。名字冲突或已有字幕被人工修改时保守保留，不直接覆盖。
- 反馈页可收集脱敏诊断包，并用默认浏览器新建 [GitHub Issue](https://github.com/tuzibuqiahuluobo/yanami-sub/issues/new)。提交前自行检查附件里的个人信息；GitHub 无法访问时可检查代理。

## 从 0.2.x 升级

本次按新依赖锁核对并重建运行环境，首个任务准备可能较慢。用户数据和模型缓存应保留。

- 自定义 model_catalog.psv 改为 model_catalog.toml。在设置中预览转换、核对变更，再备份并应用；已下线模型不会偷偷换成其他模型。
- 显式设置 FINESUB_MODEL_CATALOG 指向 PSV 时，请按上游转换命令生成 TOML，并手动更新环境变量路径；同时存在新旧目录时先人工审阅。
- [api] proxy 不支持 SOCKS，请填写代理软件的 HTTP 端口，不能用 SOCKS 端口代替。
- 旧任务显式选项会保留；精细档行为和耗时可能变化。跨核心版本续跑时部分未完成的 LLM 窗口需要重做，已交付成品不因此改写。
- 正式版默认只接收更高正式版；开启“接收预览版本更新”后可接收更高 RC。预览版默认能接收更高 RC 和正式版，不会降级。

更新分析与验证范围见 [0.7.0 合并计划](desktop/docs/core070-update-plan.md)，操作指南见 [中文使用说明](docs/usage.zh-CN.md)。

## 系统与数据

Windows 10 / 11，64 位。Whisper 建议至少 8 GB 内存；支持的 NVIDIA GPU 可加速，具体模型要求见 [上游手册](https://github.com/caca2331/finesub/tree/v0.7.0/docs/manual)。本地 MOSS 不适用于 CPU 或低于要求的显卡。

- 设置、加密 API Key、知识库与历史：%LOCALAPPDATA%/FineSub/user-data。
- 运行环境、模型、缓存、任务：默认位于安装目录，可在应用中迁移。
- 数据目录沿用 FineSub 名称，以兼容同机 CLI。卸载前先备份重要知识库、字幕与凭据。

## 开发、构建与来源

- [桌面端维护与发布](desktop/README_DEV.md) · [GitHub Actions 构建](desktop/docs/cloud-build.md)
- [核心兼容矩阵](docs/core-compatibility.md) · [来源与第三方许可](NOTICE.md)
- 核心固定提交：[7123055](https://github.com/caca2331/finesub/tree/7123055da0cd6e037d8e37feb53b82f9e428c5cb)，身份由 desktop/resources/core-source.json 管理。
- 桌面迁移锚点：[FineSub 0.5.0pre/desktop](https://github.com/caca2331/finesub/tree/0.5.0pre/desktop)。

维护者：[tuzibuqiahuluobo](https://github.com/tuzibuqiahuluobo)。FineSub 原作者 / 上游维护者：[caca2331](https://github.com/caca2331)。桌面署名贡献者：caca2331、tuzibuqiahuluobo、回不去的星光。

## 许可证

[GNU GPL v3 or later](LICENSE)。随包 FineSub prompt 模板按 [CC BY-SA 4.0](https://github.com/caca2331/finesub/blob/v0.7.0/src/finesub/llm/prompt_templates/LICENSE.md) 授权。再分发请保留来源、作者与对应许可。
