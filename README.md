# FineSub Desktop

FineSub Desktop 是 [FineSub](https://github.com/caca2331/finesub) 的 Windows 图形客户端。
本仓库从 FineSub 单仓中的 `desktop/` 独立而来，负责桌面界面、Windows 启动器、资源管理、
任务展示与应用更新；字幕处理引擎和命令行能力继续由上游 FineSub 提供。

## 项目关系与来源

- **桌面端仓库**：<https://github.com/tuzibuqiahuluobo/finesub-desktop>
- **FineSub 核心 / CLI**：<https://github.com/caca2331/finesub>
- **迁移源快照**：[`0.5.0pre/desktop`](https://github.com/caca2331/finesub/tree/0.5.0pre/desktop)
- **对应的上游正式版本**：[`FineSub v0.5.0`](https://github.com/caca2331/finesub/releases/tag/v0.5.0)
- **迁移后的发行版**：<https://github.com/tuzibuqiahuluobo/finesub-desktop/releases>

`0.5.0pre` 是桌面端从原单仓剥离前的公开迁移锚点，不是安装包版本。本仓库以该快照为基线，
后续只维护桌面端；需要新增或调整处理能力时，由 FineSub 核心 / CLI 提供稳定接口，桌面端跟随接口更新。

## 当前状态

代码快照已经迁入 `desktop/`，独立桌面端从 `0.1.0` 开始维护自己的产品版本。
当前候选版本为 `v0.1.0-rc.2`。它在首个 RC 的安装、运行和自动更新链路之上，
增加多资源并行下载、经 SHA-256 校验的本地资源复用、清华大学 TUNA 国内 Python
依赖镜像，以及发布者为 `tuzibuqiahuluobo` 的 Authenticode 发布流程。

中国大陆网络会自动使用 [清华大学 TUNA 开源软件镜像站](https://mirrors.tuna.tsinghua.edu.cn/)
的 PyPI 镜像；镜像不可用时会回退到官方源。资源安装前会在本机磁盘查找同名候选文件，
只有大小和 SHA-256 都与目标版本一致时才复用，旧版或损坏文件不会进入运行环境。

RC 构建会在打包阶段把本仓库桌面代码与上游 FineSub `v0.5.0` 的固定源码快照组合，仓库本身
不维护一份核心 / CLI 分叉。后续将继续把这段组合流程收敛为上游提供的版本化接口和构建产物。

桌面端已经覆盖单任务完整生产参数、批处理、模型路由与凭据池、知识库维护/分享、诊断、
密钥导出和大文件目录维护。仍需上游提供结构化接口的 Agent 控制、运行中批次动态入队等边界，
见 [FineSub v0.5.0 功能兼容矩阵](docs/core-compatibility.md)。

## 目录

```text
desktop/
  backend/      Python / pywebview 后端与 Windows 启动器
  frontend/     Next.js 静态界面
  installer/    Inno Setup 安装器定义
  resources/    更新配置与信任密钥
  scripts/      开发、测试和发布脚本
```

旧单仓时期的用户说明和维护说明分别保留在
[`desktop/README.md`](desktop/README.md) 与
[`desktop/README_DEV.md`](desktop/README_DEV.md)，用于迁移核对；其中涉及旧仓库目录结构的命令
需要在独立构建适配后更新。

## 作者与贡献者

- **桌面端仓库维护者**：[tuzibuqiahuluobo](https://github.com/tuzibuqiahuluobo)
- **FineSub 原作者 / 上游维护者**：[caca2331](https://github.com/caca2331)
- **原桌面端署名贡献者**：caca2331、tuzibuqiahuluobo、回不去的星光

本次迁移保留原项目署名和来源链接。更完整的变更来源可通过上游
[`0.5.0pre`](https://github.com/caca2331/finesub/releases/tag/0.5.0pre) 锚点核对。

## 许可证

本仓库从 `0.5.0pre` 迁入的代码遵循
[GNU General Public License v3.0 or later](LICENSE)（SPDX：`GPL-3.0-or-later`）。
许可证文本取自上游同一迁移锚点；
上游 FineSub 的许可说明见其
[`LICENSE`](https://github.com/caca2331/finesub/blob/v0.5.0/LICENSE)。

再分发或修改本项目时，请保留许可证、版权声明以及上述来源与作者归属。
