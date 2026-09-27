# 音频能力与本地 Agent 路由（RC7.1）

## 目标与现状

RC7 已能把 AGY、DSH、WorkBuddy、Claude Code、Codex 等本地 Agent 放入纠错路由；API 与 Agent 的基本任务流程也已跑通。但桌面任务默认请求 `video` 媒体，DSH 等纯文本 Agent 不具备音频/视频输入能力。FineSub v0.5.1 会在 `correction-mm` / `planning-mm` 过滤掉它们。不能因为某一候选具备媒体能力，就认为整个回退组都具备该能力。

另一个实现缺口是 `desktop/backend/worker/model_source.py` 只把降级后的媒体写入临时 `config.toml`，`worker/main.py` 却把原始 `TaskRequest.llm_*_media` 显式传给 `run_pipeline`，覆盖了临时配置。

## RC7.1 决策

1. API、Agent 和手动路由仍由现有 `source_route` 选取；不重做模型目录，也不虚报 DeepSeek 的音频能力。
2. 对自动生成的 Agent 回退组，只要有成员不支持本次要求的媒体，就把该任务的纠错与规划媒体降为 `text`，以保证按序回退到下一个 Agent 时仍可执行。若所有候选都支持所需媒体，保持原请求。手动模型路由遵从用户明确的媒体选择，能力不符应给出错误。
3. 有效媒体必须随 `SourceRoute` 传给 `_execute_pipeline` 的实际 `run_pipeline` 参数；只改临时配置不算修复。临时配置与参数保持一致，不能让两套来源相互矛盾。
4. 任务日志只写一次清晰提示：已使用纯文本纠错、音频/视频佐证不会交给该回退组，必要时提示可改选多模态模型。UI 不把语音识别（本地 Faster-Whisper）错称为 Agent 处理。
5. 上游 FineSub 仍固定在 v0.5.1；更新上游前先重新对照模型能力事实与路由契约，不在本仓库臆造 `supports_audio=true`。

## 验收

- 单个 DSH、Claude Code、Codex、WorkBuddy 与混合 AGY+DSH 的 Agent 组均能通过实际 `run_pipeline` 的媒体能力校验；纯文本降级可从传入参数和日志观察到。
- 全媒体能力的 AGY 组保持用户请求；显式手动路由不被悄悄降级；API 路由行为不回归。
- 健康检查只代表 CLI 存在/版本/环境可用，不声称已验证账号、额度或真实推理。

## 不做

不调用未知模型试探音频能力，不为启动前检查发起收费推理，也不把音频文件发送给文本模型。真实端到端的账号/额度验证需用户环境验收。
