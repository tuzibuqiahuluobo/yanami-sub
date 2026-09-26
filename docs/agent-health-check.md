# Agent Health Check 机制

## 概述

Agent Health Check 是在任务执行前预先检测本地 Agent 可用性的机制，用于：

1. **提前发现问题**：在耗时的 ASR 阶段之前就检测 Agent 问题
2. **明确错误原因**：清晰告知用户为什么 Agent 不可用
3. **提供操作指引**：针对不同错误类型给出具体的解决建议

## 问题背景

在引入健康检查之前，系统存在以下问题：

### 问题 1：浪费用户时间

```
用户启动任务 → ASR 处理（5-10分钟）→ 尝试调用 Agent → 发现配额不足 → 任务失败
```

ASR 阶段耗时较长，但如果 Agent 配额不足，这些时间都白费了。

### 问题 2：错误信息不清晰

原来的错误日志：
```
本地 Agent local-dsh-deepseek-v4-pro 未能使用（provider_disabled）
本地 Agent local-dsh-deepseek-v4-flash 未能使用（provider_disabled）
所有本地 Agent 均未完成纠错翻译：No eligible target for role general_capable
```

用户看到这些信息后不知道：
- 为什么 `provider_disabled`？
- 是配置问题还是配额问题？
- 应该如何解决？

### 问题 3：无预检测机制

系统直接尝试调用 Agent，失败后才报告错误。没有在任务开始前进行可用性检查。

## 解决方案

### 1. 预检测机制

在 `run_request` 开始时，对于需要 LLM 的任务（`translated-srt`、`final-srt`），先检查模型源可用性：

```python
# Pre-check: validate model source availability before expensive ASR stages
if request.stage in {"translated-srt", "final-srt"} and request.llm_source != "manual":
    emit(WorkerEvent.log(task_id, "正在检查模型源可用性..."))
    
    is_available, error_message = validate_source_availability(
        request.llm_source,
        check_agents=should_check_agents,
    )
    
    if not is_available:
        emit(WorkerEvent.log(task_id, f"模型源检查失败：{error_message}"))
        emit(WorkerEvent.failed(task_id, error_message))
        raise ValueError(error_message)
```

**效果**：
- 在 ASR 开始前就发现问题
- 节省用户时间
- 避免无意义的处理

### 2. 详细的健康检查

`check_agent_health()` 对每个配置的 Agent 执行轻量级健康检查：

```python
def _check_agent_tier(tier: str, command: str | list) -> AgentStatus:
    # 1. 检查命令是否配置
    # 2. 检查可执行文件是否存在
    # 3. 运行 --version 检查（10秒超时）
    # 4. 分析 stderr/stdout 中的错误模式
    #    - quota/配额 → quota
    #    - unauthorized/api key → auth_failed
    #    - provider disabled → provider_disabled
```

**检测的错误类型**：

| 错误类型 | 原因 | 用户可见信息 |
|---------|------|------------|
| `command_not_configured` | 命令未配置 | "命令未配置" |
| `executable_not_found` | 找不到可执行文件 | "找不到可执行文件：{path}" |
| `quota` | 配额不足/余额不足 | "配额不足或余额不足" |
| `auth_failed` | 认证失败/API密钥问题 | "认证失败，请检查 API 密钥" |
| `provider_disabled` | 提供商被禁用 | "提供商被禁用" |
| `timeout` | 健康检查超时 | "健康检查超时（10秒）" |

### 3. 清晰的错误报告

健康检查结果会生成详细报告：

```python
report = check_agent_health()
summary = report.format_summary()
# 输出：可用：LOCAL_DSH；不可用：LOCAL_AGY

detailed = report.format_detailed_report()
# 输出：
# 本地 Agent 健康检查：
#   LOCAL_DSH: ✓ 可用
#   LOCAL_AGY: ✗ 不可用 (quota)
#     详情：配额不足或余额不足
```

### 4. 可操作的指导建议

改进后的错误消息会包含操作建议：

```python
if reason == "quota":
    message += "\n  → 建议：请充值 API 配额后重试"
elif reason == "provider_disabled":
    message += "\n  → 建议：请在设置中检查该 Agent 是否被禁用，或重新运行健康检查"
elif reason == "transient":
    message += "\n  → 建议：临时错误，可能是网络问题或服务暂时不可用，请稍后重试"
```

## 使用示例

### 场景 1：配额不足

**之前**：
```
[5分钟 ASR 处理后]
本地 Agent local-dsh-deepseek-v4-flash 未能使用（quota）
所有本地 Agent 均未完成纠错翻译
```

**现在**：
```
正在检查模型源可用性...
Agent 健康检查：不可用：LOCAL_DSH
Agent LOCAL_DSH 不可用（quota）：配额不足或余额不足
  → 建议：请充值 API 配额后重试
模型源检查失败：所有配置的本地 Agent 均不可用。请在设置中检查 Agent 配置，或选择使用 API 模式。
[任务立即失败，没有浪费时间在 ASR 上]
```

### 场景 2：Provider 被禁用

**之前**：
```
[5分钟 ASR 处理后]
本地 Agent local-dsh-deepseek-v4-pro 未能使用（provider_disabled）
本地 Agent local-dsh-deepseek-v4-flash 未能使用（provider_disabled）
```

**现在**：
```
正在检查模型源可用性...
Agent 健康检查：不可用：LOCAL_DSH
Agent LOCAL_DSH 不可用（provider_disabled）：提供商被禁用
  → 建议：请在设置中检查该 Agent 是否被禁用，或重新运行健康检查
模型源检查失败：所有配置的本地 Agent 均不可用。请在设置中检查 Agent 配置，或选择使用 API 模式。
```

### 场景 3：部分 Agent 可用

如果有多个 Agent 配置，部分可用：

```
正在检查模型源可用性...
Agent 健康检查：可用：LOCAL_CLAUDE；不可用：LOCAL_DSH, LOCAL_AGY
Agent LOCAL_DSH 不可用（quota）：配额不足或余额不足
  → 建议：请充值 API 配额后重试
Agent LOCAL_AGY 不可用（executable_not_found）：找不到可执行文件：agy
[任务继续，使用 LOCAL_CLAUDE]
模型来源：agent；尝试顺序：local-claude-sonnet-5
```

## 性能考虑

健康检查设计为轻量级：

- **单个 Agent 检查**：< 1秒（运行 `--version` 命令）
- **超时保护**：10秒超时，避免长时间阻塞
- **总开销**：通常 < 10秒（对于 3-4 个 Agent）
- **相比 ASR**：ASR 阶段通常需要 5-10 分钟，健康检查开销可忽略

## 配置选项

### 快速检查 vs 完整检查

```python
# 快速检查：只验证 Agent 是否配置（不运行命令）
validate_source_availability("agent", check_agents=False)

# 完整检查：运行实际健康检查命令
validate_source_availability("agent", check_agents=True)
```

**何时使用**：
- **快速检查**：UI 表单验证、批量任务预检
- **完整检查**：任务执行前、用户点击"开始检测"按钮

## 实现细节

### 核心模块

- **`agent_health_check.py`**：健康检查核心逻辑
  - `check_agent_health()` - 检查所有配置的 Agent
  - `_check_agent_tier()` - 检查单个 Agent
  - `validate_source_availability()` - 验证模型源可用性

- **`main.py`**：集成到任务流程
  - 在 `run_request()` 开始时调用健康检查
  - 记录详细的检查结果到任务日志
  - 为失败的 Agent 添加操作建议

- **`model_source.py`**：增强日志
  - 当 targets 为空时记录详细的诊断信息
  - 包含环境变量状态、API 密钥配置等

### 错误检测逻辑

通过分析 CLI 输出中的关键词来判断错误类型：

```python
# 配额错误
if any(marker in combined for marker in [
    "insufficient balance", "quota exceeded", "quota",
    "余额不足", "配额",
]):
    return AgentStatus(..., reason="quota", ...)

# 认证错误
if any(marker in combined for marker in [
    "unauthorized", "authentication", "api key",
    "未授权", "认证",
]):
    return AgentStatus(..., reason="auth_failed", ...)

# Provider 禁用
if any(marker in combined for marker in [
    "provider disabled", "backend unavailable",
    "提供商被禁用",
]):
    return AgentStatus(..., reason="provider_disabled", ...)
```

## 测试

测试覆盖：
- 单元测试：`test_agent_health_check.py`
- 覆盖所有错误类型检测
- Mock subprocess 调用
- 验证错误消息格式

运行测试：
```bash
pytest desktop/backend/tests/test_agent_health_check.py -v
```

## 未来改进方向

1. **缓存健康检查结果**：避免短时间内重复检查
2. **后台定期检查**：应用启动后定期刷新 Agent 状态
3. **更细粒度的能力检查**：检测 Agent 是否支持音频、视频等特定能力
4. **配额余额显示**：显示剩余配额/余额（如果 Agent CLI 支持）

## 相关文档

- [core-compatibility.md](./core-compatibility.md) - FineSub 核心兼容性
- [local-agents.md](./local-agents.md) - 本地 Agent 配置指南
