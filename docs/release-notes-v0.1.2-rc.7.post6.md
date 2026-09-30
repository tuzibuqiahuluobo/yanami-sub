# Yanami Sub 0.1.2 RC7.6

RC7.6 改进任务日志时间戳，修复 Python 解释器文件选择器，并防止重装/更新恢复后混用新启动器与旧任务引擎。字幕核心继续固定为 FineSub v0.5.1，本版不升级上游核心。

## 修复与改进

- 单任务的实时界面与 `task-log.txt`、批处理的 `batch-log.txt` 逐行显示事件原始时间，包含日期、毫秒和 UTC 时区偏移。多行报错与 Traceback 的每一行都有时间戳；导出日志原样复制，不改成导出时间。中英文、日文及 UTF-8 内容保持原样。
- 修复“指定解释器”使用了 pywebview 不接受的文件筛选格式，导致在创建原生窗口前失败。可选择 `.exe`，选择后仍验证它是否为可用的 CPython 3.12；筛选器不代表任意 EXE 都可以用作解释器。
- 文件选择或解释器验证失败时，在当前 Python 安装弹窗内显示错误；取消选择保留已检测到的解释器。诊断刷新失败不会否定已经保存的选择。
- 修复今日反馈中的 `TaskRequest.llm_agent: Extra inputs are not permitted`：日志指向旧 `app/versions/0.1.0-rc.7` worker，而冻结启动器已发送新参数。恢复只选择完整且不低于打包启动器基线的快照，健康回退也检查完整性与兼容性，不靠丢弃用户的 Agent 选择来规避错误。
- 在加载上游代码之前完成健康回退，并避免同一次启动重复消耗健康检查尝试。单任务与批处理均从最终选中的活动目录建立 worker 上下文；活动指针读取统一兼容 UTF-8 BOM，避免恢复、核心、界面与版本显示读取结果不一致。
- 保留 RC7.5 对 Python 字节码缓存导致完整性误报、反复回滚旧版本、更新说明窄列和系统日志入口的修复。

## 升级说明

- 版本号为 `0.1.2-rc.7.post6`，预览通道为 `beta`。RC 用户默认可接收更新；0.1.1 正式版用户需先开启“设置 → 应用更新 → 接收预览版本更新”。
- 同一批修复也以 `0.1.1.post1` 正式热修版发布，正式版用户无需开启预览更新。
- 本次修改涉及冻结启动器，构建脚本默认使用目标版本作为 `minimumLauncherVersion`，本 RC 为 `0.1.2-rc.7.post6`，使旧启动器使用完整更新包。发行时不得降低此下限或把 app-only ZIP 当作旧启动器的升级包。
- 如旧安装无法启动，退出 Yanami Sub 后运行本版安装器，选择原目录覆盖安装。无需先卸载或删除现有任务、模型、缓存与个人设置。
- 若没有任何完整兼容的 app 快照，应用会拒绝混用旧引擎；此时应覆盖安装完整包，不能手工把 `current.json` 指向任意旧目录。

## English summary

- Adds original event timestamps, milliseconds and UTC offsets to every task/batch log line, including multiline tracebacks. Exports preserve the saved log unchanged.
- Fixes the native Python file-picker filter. Selection errors stay visible in its modal, cancellation preserves discovery, and selected executables still require CPython 3.12 validation.
- Prevents a new frozen launcher from using an older incompatible worker after reinstall or recovery. Health rollback is validated and completes before core imports; single tasks and batches use the same selected snapshot.
- Requires a full update with `minimumLauncherVersion=0.1.2-rc.7.post6`. In-place installation preserves existing data. Stable users must opt into preview updates.
