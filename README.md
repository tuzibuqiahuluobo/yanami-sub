# Yanami Sub

基于 [FineSub](https://github.com/caca2331/finesub) 的 Windows 桌面字幕工作台。

```text
音频 / 视频 / URL → 人声分离 → VAD + ASR → 字幕稳定化 → LLM 纠错翻译 → SRT
```

Yanami Sub 为 FineSub 的处理能力提供图形界面、批处理、资源管理、知识库与应用更新。
字幕核心与命令行仍由上游 FineSub 维护；本仓库不复制或分叉核心实现。

## 快速开始

1. 从 [Releases](https://github.com/tuzibuqiahuluobo/yanami-sub/releases) 下载
   `Yanami-Sub-0.1.0-rc.6.post1-Setup.exe`。
2. 退出正在运行的旧版 FineSub Desktop，然后运行安装器。
3. 启动 Yanami Sub，在“设置”中填写需要的 API Key，或配置本机 Agent。
4. 点击“新建任务”，选择本地媒体或粘贴 URL，选择目标阶段后开始处理。

首次使用相关阶段时，程序会准备隔离的 Python 3.12、FFmpeg 和模型资源，完整环境约需
5 GB。下载器会先扫描本机可用资源并核对大小与 SHA-256；缺失资源可并行下载。中国大陆
网络的 Python 依赖会优先使用
[清华大学 TUNA 镜像](https://mirrors.tuna.tsinghua.edu.cn/)，失败时回退官方源。
准备 Python 前会在后台检查本机可复用的 64 位 Python 3.12（最长约 12 秒），并明确提供
“使用本机 Python”“指定解释器”或“下载私有 Python”三种选择。

> `v0.1.0-rc.6.post1`（RC6.1）是预览版。RC5 至 RC6 可在“应用更新”中检查并升级；
> 旧版 FineSub Desktop 与 RC4 用户需要手动运行 RC6.1 安装器覆盖升级。
> 每个桌面 Release 均同时提供在线更新清单和签名。请从本仓库 Release 下载并按页面
> 提供的 SHA-256 校验。

## 能做什么

- 单任务：本地音频、视频或 URL 输入，完整暴露 FineSub 的识别、稳定化、翻译与知识参数。
- 批处理：混合本地文件和 URL，设置下载 / ASR / LLM 并发、优先级、重试与断点续跑。
- 模型路由：Gemini 免费 / 付费池、自定义服务商、本机 Agent 和按任务覆盖。
- 知识库：浏览、修订、任务反馈、材料蒸馏、冲突处理、共享与维护者审核。
- 资源管理：依赖诊断、多资源并行下载、本地复用、日志查看和大文件目录迁移。
- 输出管理：本地媒体只把可交付的 `.srt` 字幕发布到源文件旁，内部产物留在受管任务目录。
- 应用更新：启动公告优先提供应用内下载，历史版本按需展开，GitHub 完整安装器作为备用入口。

各页面的实际操作、数据位置和常见问题见
[中文使用说明](docs/usage.zh-CN.md)。桌面与核心的功能边界见
[FineSub v0.5.1 兼容矩阵](docs/core-compatibility.md)。

## 系统要求

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11，64 位 |
| 内存 | ASR 建议至少 8 GB；仅 LLM 阶段建议至少 4 GB |
| 显卡 | 人声分离与 ASR 建议 RTX 20 系或更新、显存至少 4 GB；部分阶段可回退 CPU |
| 网络 | 首次准备运行环境、模型、URL 下载和在线 LLM 时需要 |
| 磁盘 | 完整运行资源约 5 GB，模型和缓存可迁移到其他磁盘 |

更完整的显卡、模型和资源要求以 FineSub 上游的
[资源说明](https://github.com/caca2331/finesub/blob/v0.5.1/docs/manual/resources.md) 为准。

## 数据与上游共享

- 设置、API Key、知识库和任务历史：`%LOCALAPPDATA%\FineSub\user-data`
- 运行环境、模型、缓存和任务目录：默认位于安装目录，也可以在应用内迁移
- 本地输入的可交付字幕：源媒体所在目录

保留 `FineSub` 用户数据目录是有意的兼容设计：Yanami Sub 与同机安装的 FineSub CLI
可以共享设置和知识库，不会因产品改名而丢失已有数据。

## 项目关系

- **Yanami Sub 仓库**：<https://github.com/tuzibuqiahuluobo/yanami-sub>
- **FineSub 上游 / CLI**：<https://github.com/caca2331/finesub>
- **当前固定核心版本**：[`FineSub v0.5.1`](https://github.com/caca2331/finesub/tree/v0.5.1)
- **桌面端迁移锚点**：[`FineSub 0.5.0pre/desktop`](https://github.com/caca2331/finesub/tree/0.5.0pre/desktop)

桌面端从 FineSub `0.5.0pre` 的 `desktop/` 目录独立出来，从 `0.1.0` 开始维护自己的版本号。
需要新的处理能力时，优先由上游 FineSub 提供稳定接口，Yanami Sub 再跟进接入。

## 文档

- [中文使用说明](docs/usage.zh-CN.md)
- [桌面端维护与发布](desktop/README_DEV.md)
- [核心功能兼容矩阵](docs/core-compatibility.md)
- [来源与第三方许可](NOTICE.md)
- [FineSub 上游文档](https://github.com/caca2331/finesub/tree/v0.5.1/docs/manual)

## 作者与贡献者

- **Yanami Sub 维护者**：[tuzibuqiahuluobo](https://github.com/tuzibuqiahuluobo)
- **FineSub 原作者 / 上游维护者**：[caca2331](https://github.com/caca2331)
- **桌面端署名贡献者**：caca2331、tuzibuqiahuluobo、回不去的星光

## 许可证

Yanami Sub 遵循上游当前使用的
[GNU General Public License v3.0 or later](LICENSE)（SPDX：`GPL-3.0-or-later`）。
本仓库保留上游来源、作者和许可证信息。随包分发的 FineSub prompt 模板另按其目录中的
[CC BY-SA 4.0](https://github.com/caca2331/finesub/blob/v0.5.1/src/finesub/llm/prompt_templates/LICENSE.md)
授权。再分发或修改时请一并保留对应声明。
