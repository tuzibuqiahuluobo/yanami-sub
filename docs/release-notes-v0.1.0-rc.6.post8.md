# Yanami Sub 0.1.0 RC6.8

RC6.8 改善深色界面的可读性，并修复使用 SOCKS 代理时 AI 模型权重下载因缺少
`socksio` 而失败的问题。内部版本为 `0.1.0-rc.6.post8`；字幕处理核心仍固定为
[FineSub v0.5.1](https://github.com/caca2331/finesub/tree/v0.5.1)。

## 本版更新

- 深色模式改为低眩光的深灰底色和中性分层卡片，仍可调节背景不透明度；资源页下载日志、状态标签、
  输入控件和提示框不再混用亮白背景。浅色模式保留原有风格。
- 随应用包提供经 SHA-256 校验的轻量 `socksio` wheel；模型预下载和正常任务
  共用的隔离 Python 启动路径均能使用 SOCKS 代理，无需重装约 2.8 GB 的 AI 依赖。
- 保留原有模型缓存、镜像线路、代理配置和用户数据；不改变上游 FineSub 核心。

## 安装与更新

- 可以在现有 RC6.7 中打开“设置 → 应用更新”下载 RC6.8；本次包含启动窗口配色
  调整，因此使用完整更新包。若 RC6.7 无法正常打开，
  或 GitHub 网络不可达，请下载 `Yanami-Sub-0.1.0-rc.6.post8-Setup.exe` 与同名
  `.sha256`，核对哈希后覆盖安装。
- RC6.6 若启动时遇到 WinError 448，也需使用本版 Setup 覆盖安装；无需先卸载或
  删除用户的 Claude Code、Python、代理设置和模型缓存。
- RC4 或旧版 FineSub Desktop 请使用 Setup 覆盖安装。

本 Release 同时提供安装器、应用包、完整包、SHA-256 文件，以及项目密钥签名的
在线更新清单。安装包不使用付费 Authenticode 证书签名。

## 许可

Yanami Sub 遵循 `GPL-3.0-or-later`。打包的 SOCKSIO wheel 采用 MIT 许可证；
来源、作者和第三方许可见
[NOTICE](https://github.com/tuzibuqiahuluobo/yanami-sub/blob/main/NOTICE.md)。
