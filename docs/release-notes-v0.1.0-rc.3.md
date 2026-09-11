# Yanami Sub 0.1.0 RC3

这是项目从 **FineSub Desktop** 整体改名为 **Yanami Sub** 后的首个迁移预览版。

## 本版内容

- 产品、窗口、托盘、可执行文件、安装器、快捷方式、包元数据和仓库统一使用 Yanami Sub；
- 跟进并固定 FineSub `v0.5.1` 核心；
- 安装器界面固定为简体中文；
- 旧 FineSub Desktop 安装可原位迁移，完成后只保留 `Yanami Sub.exe`；
- 新的 Yanami Sub 更新清单与资产命名，避免旧客户端误安装不兼容的改名包；
- 多资源并行下载、磁盘本地复用与清华 TUNA Python 依赖镜像；
- 单任务高级参数、批处理、路由与凭据池、知识库维护 / 分享、诊断与数据维护；
- 改进知识库页面的密度、对齐和窄窗口响应式布局；
- 新增完整中文 README、使用说明、上游来源和许可说明。

## 安装

1. 退出旧版 FineSub Desktop，包括系统托盘中的后台进程。
2. 下载 `Yanami-Sub-0.1.0-rc.3-Setup.exe` 与同名 `.sha256`。
3. 使用 `Get-FileHash` 校验 SHA-256 后运行安装器。

RC3 保留原 AppId 以覆盖旧版，并删除旧名称的主程序、更新器和快捷方式。共享数据仍位于
`%LOCALAPPDATA%\FineSub\user-data`，不会因改名而丢失。

## 预览版说明

- 本版为 prerelease；处理核心来自 [FineSub v0.5.1](https://github.com/caca2331/finesub/tree/v0.5.1)。
- 当前构建环境没有受信任的 Authenticode 证书，因此安装包未签名。请只从本仓库下载并核验
  Release 附带的 SHA-256。
- 从 FineSub Desktop 到 Yanami Sub 的这一次改名需要手动运行安装器；RC3 之后可使用新的
  Yanami Sub 应用内更新通道。

## 许可与来源

Yanami Sub 遵循上游当前的 `GPL-3.0-or-later`。详细作者、迁移来源与 prompt 模板许可见
[NOTICE](../NOTICE.md)。
