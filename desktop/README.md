# FineSub Desktop

> 本文由原 FineSub 单仓的桌面端说明迁入。独立仓库的来源、作者、许可证和迁移状态请先看
> [仓库根 README](../README.md)。

FineSub Desktop 是 FineSub 的可选 Windows 客户端：用图形界面创建任务、管理资源、
查看日志。它跑的是同一套 pipeline（`src/finesub/pipeline.py`，在隔离的
worker 进程里），**不取代命令行**——同一台机器上装了 CLI 的话，两边共用设置、
API Key 和知识库。

## 安装

从 [Releases](https://github.com/tuzibuqiahuluobo/finesub-desktop/releases) 取任一种：

- `FineSub-Desktop-<版本>-Setup.exe` —— 安装器，写开始菜单与卸载项。
- `finesub-full-<版本>-win-x64.zip` —— 解压即用，不写注册表。

首次运行会自动下载并安装隔离的 Python 3.12 运行环境与 AI 依赖（约 5 GB）、
FFmpeg，模型按需下载。这一步在应用内有进度与日志；装不上时可以暂停后重试。

## 数据放在哪

- **设置、API Key、知识库、任务历史** → `%LOCALAPPDATA%\FineSub\user-data`。
  安装版、便携版和 pip 安装的 CLI **共用这一份**，所以换个入口不会变成另一套知识库。
- **运行环境、模型、下载缓存、任务产物** → 默认跟着安装目录走，可以整体搬到别的盘，
  也可以让多个安装共用一份，不必重复下载。

搬盘、共用、卸载时删哪些，见上游
[`docs/manual/resources.md`](https://github.com/caca2331/finesub/blob/v0.5.0/docs/manual/resources.md)。
API Key 的配置见上游
[`docs/manual/env.md`](https://github.com/caca2331/finesub/blob/v0.5.0/docs/manual/env.md)。

## 界面能设什么

桌面端覆盖单个任务的完整生产路径。一次任务里能在界面上选的：

| 界面上有 | 对应的命令行选项 |
| --- | --- |
| 输入文件 / URL、输出名 | 输入、`--name`、`--no-download-video` |
| 跑到哪一步 | `--stage` |
| 识别模型 | `--model` |
| 语言 | `--language` |
| 处理设备(自动 / 显卡 / CPU)、用哪张卡 | `--device`(选卡是桌面独有,命令行用 `CUDA_VISIBLE_DEVICES`) |
| 显卡档位 | `--gpu-tier` |
| 背景信息、翻译风格、命名样式 | `--extra-info`、`--extra-style`、`--style`、`--style-mode` |
| 知识库与人工精修反馈 | `--knowledge`、`--refined-srt`、`--task-summary` |
| LLM 媒体 / 检索 / 难度 / 连续性 / 并发 / 路由 / 重试 | `--llm-*`、两个窗口重试预算 |
| 分离、VAD、二次校验、上下文、解码、稳定化与后处理 | 对应的全部生产调优选项 |
| 跑完清理中间产物 | (命令行不清,产物留在原地) |
| 设置页:字幕长度偏好 | `--split-length-scale` / `config.toml` 的 `[segmentation] length_scale` |

批处理页面支持多个本地文件和 URL、下载/识别/LLM 并发、队列背压、优先级、失败隔离、
阶段重试、取消和断点续跑；模型路由与知识库有各自的高级管理页面。

⚠ **有一处有意采用更积极的桌面默认值**，同一个文件两边直接运行时需要留意：

| | 桌面端 | 命令行 |
| --- | --- | --- |
| 知识库 | `update`（跑完写回本次发现） | `collect`（收集反馈但不写回） |

完整的支持范围、刻意保留在 CLI 的终端/开发能力，以及希望上游补充的结构化接口，见
[核心兼容矩阵](../docs/core-compatibility.md)。当前主要 CLI 专属项是 Agent join/task 控制、
向运行中 JSONL manifest 动态追加任务，以及 `--test-profile` 等开发开关。

## 命令行

独立后的桌面安装包不再附带旧的 `finesub.cmd` 包内壳。需要批处理、脚本调用或更细的参数时，
请安装上游 [FineSub CLI](https://github.com/caca2331/finesub)。两端继续共用用户数据，
桌面端只消费上游提供的稳定接口，不在本仓库复制一套 CLI 实现。

## 更新

应用内检查并安装：小版本只换应用层（重启生效），大版本换整个安装（需要先退出
FineSub，由随包发布的 updater 完成）。个人数据、模型、缓存、任务产物都会保留。
也可以到 Release 页手动下载。

---

维护者请看 [README_DEV.md](README_DEV.md)：架构、依赖与 lock、外部工具、开发环境、
测试、构建与签名发布。
