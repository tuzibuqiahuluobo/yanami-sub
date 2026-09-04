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

代码快照已经迁入 `desktop/`。这是独立仓库的迁移基线，目标版本为 `0.5.0`。
原快照的构建脚本仍依赖旧单仓根目录中的 FineSub 源码、运行时锁和 manifest；在独立构建适配完成前，
请不要把当前 `main` 当作可发布安装包。这个限制不会通过复制一份核心源码来绕过，桌面端将改为消费
上游 FineSub 提供的版本化接口和构建产物。

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
