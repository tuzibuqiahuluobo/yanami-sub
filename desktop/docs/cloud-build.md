# GitHub Actions 云端构建

工作流：`.github/workflows/build-windows.yml`，名称 **Build Windows installer**。
只接受手动运行，不响应 push/tag，不创建 Release，不修改用户更新频道。
测试、前端构建、PyInstaller 和 Inno Setup 均在 GitHub 的 Windows runner 中执行，不占用本地构建资源。
FineSub 固定为 v0.5.1；版本取选中分支的已提交 VERSION，不在 CI 临时改号。

## 使用

1. 将工作流与改动合并到仓库默认分支后，在 GitHub → Actions 选上述工作流。
2. 点击 Run workflow，选择要构建的已提交分支。普通安装包不勾选 signed_updates。
3. 运行完成后，在该次运行的 Artifacts 下载产物（需登录 GitHub，保留 14 天）。
4. 产物含 Setup 安装包及 SHA-256、便携版 ZIP；安装包不会自动发布给用户。

普通构建无需私钥。打包仍携带仓库内的公开可信更新公钥，未配置 Authenticode 证书时安装包没有 Windows 发布者证书签名；SHA-256 不是签名。当前流程不下载 AI 权重、不调用用户 Agent、不运行真实模型任务。

## 可选：生成应用内更新资产

在仓库 Settings → Environments 创建 **release-build**，限制仅可信发布分支可运行，并配置审批规则。先配置保护再加入私钥；不要把私钥设置为无保护的普通仓库变量。
在该环境的 Secrets 添加 `YANAMI_RELEASE_PRIVATE_KEY`，值为原有 Ed25519 PEM 私钥；不要提交 `.pem` 到仓库，也不要把密钥写到工作流、Artifacts 或日志。

勾选 signed_updates 后，密钥仅在签名步骤提供，写到 runner 临时目录，退出该步骤时清理。工作流先核对私钥对应的公钥与产品内置的 trust anchor，再复用 build-release.ps1 生成 ZIP、校验和、在线更新 JSON 和签名；仍不创建 Release。
现有多密钥轮换需先增加显式 key-id 选择，工作流不会猜测或生成替代密钥。

云端生成资产后仍需另行检查、手动发布；只有发布到正确仓库/频道且版本更高，客户端才会提示更新。请不要用未审核的分支执行携带签名密钥的构建。

## 限制与回退

- 首次没有 npm 缓存会较慢；后续仅复用 npm 缓存，不缓存个人数据或签名文件。
- Windows runner 的空间、网络和 Actions 使用额度受 GitHub 限制；失败时可查看具体步骤后重新手动运行。
- 构建脚本仍可本地使用；此工作流不改变本地发布工具，不自动上传本机凭据。
- 正式发布前应在真实 Windows 机器验证安装、升级、卸载及至少一轮实际字幕任务；云端打包成功不等于 GPU/账号流程均经过实测。

参考：[GitHub-hosted runners](https://docs.github.com/en/actions/how-tos/manage-runners/github-hosted-runners/use-github-hosted-runners)、[workflow artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)。
