# Yanami Sub 0.1.0 RC6.7

RC6.7 修复部分 Windows 设备安装 RC6.6 后，启动时检查本地 Claude Code 路径触发
`WinError 448`，导致主窗口尚未打开就退出的问题。内部版本为 `0.1.0-rc.6.post7`；
字幕处理核心仍固定为 [FineSub v0.5.1](https://github.com/caca2331/finesub/tree/v0.5.1)。

## 本版更新

- 本地 Agent 扫描遇到不可访问的 npm 路径时跳过该候选，继续检测其他可用安装。
- 即使可选 Agent 扫描发生文件系统异常，也不再阻止 Yanami Sub 主界面启动。
- 不更改用户的 Claude Code、Cargo、Python 环境和个人数据；不改变上游字幕核心。

## 安装与更新

- **RC6.6 打不开的用户**：从本 Release 下载
  `Yanami-Sub-0.1.0-rc.6.post7-Setup.exe` 和同名 `.sha256`，核对哈希后直接覆盖安装。
  无需先卸载 RC6.6；由于旧程序进不了界面，不能依赖它的应用内更新按钮。
- RC6.6 能正常打开的用户：可在“设置 → 应用更新”检查 RC6.7；本次修复了冻结启动器，
  因此在线更新使用完整包。若网络或 GitHub 接口异常，请使用上述 Setup。
- RC4 或旧版 FineSub Desktop：也请用 Setup 覆盖安装。

本 Release 同时提供安装器、应用包、完整包、SHA-256 文件及签名的在线更新清单。
安装包不做付费 Authenticode 证书签名；在线更新清单仍由项目密钥签名以校验包的完整性。

## 许可

Yanami Sub 遵循上游当前的 `GPL-3.0-or-later`。作者、迁移来源和第三方许可见
[NOTICE](https://github.com/tuzibuqiahuluobo/yanami-sub/blob/main/NOTICE.md)。
