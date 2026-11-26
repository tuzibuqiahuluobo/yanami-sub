# Yanami Sub 0.3.2 正式版

Windows x64 正式版，核心仍为 FineSub 0.7.1。包含 0.3.2 系列预览版的功能，以及本次反馈附件区的界面优化。

- **反馈附件更好用**：用宽松的拖放区和明确的「选择文件」取代浏览器默认控件。已选截图与日志有独立文件行，任务/批次日志可折叠，打包按钮与隐私提示单独展示。
- **结构化问题报告**：按重现步骤、预期结果、实际结果和版本生成 Issue 草稿，可在本机预览并打包日志。支持在默认浏览器提交；使用已登录的 GitHub CLI 可直接提交审阅过的正文与脱敏摘要，具备 `--attach` 时还可带截图。完整 ZIP 仍由用户在浏览器选择附加。
- **保留诊断信息**：自动或手动清理中间产物前，记录阶段、产物种类以及大小，不保留原始音视频、字幕正文或模型会话。任务/批次日志支持每页十条浏览。
- **Tooltip 与动效**：说明气泡扩展到知识库、资源、设置、工具和反馈页，必填条件和风险仍直接显示。开始按钮、页签、开关、输入框与完成通知等提供轻量反馈，支持关闭动效。

0.3.1.post1 正式版及 0.3.2 RC1.2 可通过应用内完整更新直接升级。无需先卸载，也无需清空任务、模型或知识库。

## English

- Redesigned feedback attachments with a dedicated drop zone, clear file picker, selected-file rows, collapsible logs and a separate packaging action.
- Review a structured Issue draft and local diagnostic ZIP before sharing. Optional GitHub CLI publishing uses the reviewed content.
- Keep artifact roles and sizes before cleanup, without retaining their contents. Tooltips and local control motion respect reduced-motion preferences.
