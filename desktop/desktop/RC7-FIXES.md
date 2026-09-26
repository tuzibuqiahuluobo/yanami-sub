# RC7 修复说明

根据 Issue #1 的审计报告，RC7 修复了以下10个问题：

## 高优先级修复

### 问题1：Agent 路由质量检查 (desktop/backend/worker/model_source.py)
- **问题**：RC6.11+ 使用组成员身份判断，导致 Claude Code 和 Codex 被排除
- **修复**：改用 `quality_score >= floor` 判断，符合上游 FineSub 的质量下限机制
- **影响**：所有满足质量要求的 Agent（包括 Claude Code、Codex）现在都可用于纠错

### 问题2：媒体类型自动降级 (desktop/backend/worker/model_source.py)
- **问题**：桌面端默认 `video` 媒体，DSH/WorkBuddy/Claude Code/Codex 都是纯文本模型，能力校验后无候选
- **修复**：实现自动降级机制 - 当 Agent 不支持所需媒体类型时，自动降为 `text`
- **影响**：纯文本 Agent 现在可以正常工作，任务日志会说明已启用纯文本模式

## 中优先级修复

### 问题3：API 异常处理 (desktop/backend/worker/main.py)
- **问题**：API 来源的任何异常都被吞掉，报告为「纠错失败，已保留原始字幕」
- **修复**：检查永久失败类型（无效 API key、认证错误等），这些错误会明确失败而不是被掩盖
- **影响**：配置错误现在会被正确报告，不再被掩盖成"成功"

### 问题4：发布工程 (VERSION 文件已更新为 0.1.0-rc.7)
- **说明**：VERSION 文件已正确更新，遵循 PEP 440 版本格式

### 问题5：误提交预防 (desktop/.gitignore)
- **问题**：codex/rc6-ui-feedback 分支有 44,333 个文件的误提交
- **修复**：在 .gitignore 添加 tmp/、output/、out/、deliverables/、.pytest-*/ 等规则
- **影响**：防止临时文件、测试产物和用户隐私信息被提交

### 问题6：盘符根目录安全 (desktop/backend/settings/local_agents.py)
- **问题**：扫描所有盘符根目录的 `X:\deepseek-harness\apps\cli\lib\bin.js`，存在代码执行风险
- **修复**：移除 `_windows_drive_roots()` 扫描，只检查用户目录下的位置
- **影响**：关闭了本地权限提升攻击向量

### 问题7：覆盖用户修改的字幕 (desktop/backend/worker/main.py)
- **问题**：重新发布时会不经提示覆盖用户手改过的 .srt 文件
- **修复**：检查文件的 size 和 mtime，只在文件未被修改时才替换
- **影响**：用户手动修改的字幕文件不会被意外覆盖

## 低优先级修复

### 问题8：API 模型顺序 (desktop/backend/worker/model_source.py)
- **问题**：API 分支按目录顺序遍历，且将低于纠错下限的 lite 混入 quality 组
- **修复**：使用 correction-capable 组的顺序，并过滤不满足质量下限的模型
- **影响**：模型尝试顺序现在符合上游推荐（如 3.7 优先于 3.8）

### 问题9：测试修复 (desktop/backend/tests/test_model_source.py)
- **问题**：test_agent_unvetted_tier_excludes_non_correction_targets 测试使用了错误的判据
- **修复**：更新测试以使用 quality_score 判断而不是组成员身份
- **影响**：测试现在与新的路由逻辑一致

### 问题10：开发环境变量安全 (desktop/backend/launcher/main.py)
- **问题**：生产版本也响应 YANAMI_SUB_DEV_URL 环境变量
- **修复**：在 frozen 构建中忽略该环境变量
- **影响**：防止多用户场景下的本地权限提升

## 未直接修复的问题

### 问题5（分支清理）
- **状态**：codex/rc6-ui-feedback 分支仍存在于远端
- **建议**：维护者需要手动删除或重写该分支

## 验证建议

1. 使用真实 Agent 账号进行端到端纠错测试
2. 测试 DSH、WorkBuddy、Claude Code、Codex 的纠错功能
3. 验证 API 无效密钥时的错误报告
4. 测试重新发布不会覆盖用户修改的字幕

## 变更文件清单

- desktop/backend/worker/model_source.py - 问题 1, 2, 8
- desktop/backend/worker/main.py - 问题 3, 7
- desktop/backend/settings/local_agents.py - 问题 6
- desktop/backend/launcher/main.py - 问题 10
- desktop/backend/tests/test_model_source.py - 问题 9
- desktop/.gitignore - 问题 5
- VERSION - 问题 4 (已是正确值)
