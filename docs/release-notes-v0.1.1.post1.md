# Yanami Sub 0.1.1.post1

首个正式版的首次热修，与 0.1.2 RC7.6 共用修复代码。字幕核心仍固定为 FineSub v0.5.1，不升级上游核心。

## 修复与改进

- 单任务实时日志、`task-log.txt` 和批处理 `batch-log.txt` 逐行加入原始事件时间，包含日期、毫秒与 UTC 时区偏移。多行错误与 Traceback 每行均有时间戳，中英文及其他 UTF-8 内容保持原样；导出保留原始日志时间。
- 修复“指定解释器”无法打开原生文件选择窗口的问题。选择后仍校验可用的 CPython 3.12；取消不清空已检测的解释器，错误直接显示在当前弹窗中。
- 修复重装/更新恢复后新启动器调用旧 worker 导致 `llm_agent: Extra inputs are not permitted`。活动快照与健康回退均检查完整性和启动器兼容性，在加载核心之前完成恢复；单任务与批处理共用最终选中的版本。
- 活动指针读取兼容 UTF-8 BOM，避免版本显示、界面与任务引擎读取不一致。
- 恢复只选择与冻结启动器相同通道的兼容快照，避免正式热修版误用数字版本更高的残留 RC 目录；切换通道仍使用完整更新。
- 纳入此前 RC7.5 对字节码缓存完整性误报、更新后反复回滚旧版本、更新说明窄列和设置底部系统日志路径/打开位置的修复。

## 升级说明

- 版本号 `0.1.1.post1`，正式通道 `stable`，不是预览版。0.1.1 正式版用户默认收到本版，不需要开启“接收预览版本更新”。
- 本次涉及冻结启动器，`minimumLauncherVersion=0.1.1.post1`，旧版本应用内升级使用完整更新包。不要把仅应用 ZIP 当作旧启动器的升级包。
- 如旧安装无法启动，退出程序后运行 `Yanami-Sub-0.1.1.post1-Setup.exe`，选择原安装目录覆盖安装。无需卸载或清空任务、设置、模型及缓存。
- 若没有完整兼容的活动快照，应用不会混用旧任务引擎；请覆盖安装，不要手工把 `current.json` 指向任意旧目录。
- 正式版默认继续只接收正式版；开启预览更新后可升级到数字版本更高的 `0.1.2-rc.7.post6`。已有 0.1.2 RC 用户继续接收最新 RC，不会自动降级到本热修版。
- Release 提供完整安装器、完整更新包、仅应用包、SHA-256 文件及 Ed25519 签名更新清单。清单签名用于验证更新内容完整性，不是付费 Authenticode 证书。

## English summary

- First stable hotfix, sharing RC7.6 fixes and retaining the pinned FineSub v0.5.1 core.
- Adds original timestamps, milliseconds and UTC offsets to each single-task/batch log line, including multilingual tracebacks. Exports preserve those timestamps.
- Fixes the native Python interpreter picker, keeps discovery on cancellation and shows errors inside the modal. Selected executables still require CPython 3.12 validation.
- Prevents a new frozen launcher from selecting an incompatible old worker after reinstall or recovery; validated health rollback finishes before core imports.
- Includes bytecode integrity, update rollback, update-note layout and System Logs fixes.
- Stable installs receive this release without preview opt-in. Older launchers use the full package (`minimumLauncherVersion=0.1.1.post1`). In-place installation preserves data. Preview users stay on the newer 0.1.2 RC line.
