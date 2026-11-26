# Yanami Sub 0.3.2 RC1.2

Windows x64 预览版。核心仍为 FineSub 0.7.1；正式版仍为 0.3.1.post1。

- **说明气泡扩展**：知识库、资源、设置、工具和反馈页现在也有问号提示。必填条件、风险和错误仍直接显示。
- **反馈报告**：选择任务日志、截图或文本附件后，在本机生成诊断 ZIP 和可审阅的标准 Issue 草稿。登录 GitHub CLI 后可直接提交正文和脱敏摘要；支持 `--attach` 的版本也可提交截图。完整 ZIP 仍可在默认浏览器手动附加。应用不会在打包时上传文件。
- **保留诊断信息**：自动和手动清理中间产物前保留阶段、产物种类及大小，覆盖单任务与批处理。记录不包含原始音视频、字幕正文或模型会话。反馈日志列表修正为每页 10 条。
- **动效扩展**：开关、复选框、主题选中项、滑块、输入框、进度条和成功通知新增局部反馈。应用动效开关和系统「减少动态效果」都能关闭新增动效。

已有 RC1.1 可直接升级。正式版用户需开启「接收预览更新」才会收到本次更新。

## English

- Tooltips now cover Knowledge, Resources, Settings, Tools and Feedback.
- Build and review a local diagnostic ZIP and structured issue draft. Signed-in GitHub CLI can submit the reviewed body and optionally screenshots when attachment support is available; the full ZIP is attached in the browser.
- Retain artifact roles and sizes before cleanup without retaining their contents. Task-log selection now pages correctly.
- Expanded local interaction effects respect both the app's animation toggle and the system's reduced-motion setting.
