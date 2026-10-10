# MCP_HCL 当前交接

当前源码位于本地 main，版本 0.5.0，完整交付仍 **Incomplete**，`full_live_gate_passed=false`。使用入口见 [README](README.md)，维护文档见 [docs/README](docs/README.md)。

## 当前版本与证据

候选：`C:/Users/Public/Documents/MCP_HCL_Normalized_20261011_ccf9210a/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`2c57afcdf7b0f5234a738a255c5b904e15d52a000e6ab7f5f6aacd6af9e5880a`。57 个包文件与规范化源码逐字节一致；软件结果为 330 项、329 通过、1 权限跳过，候选专项 177 项、176 通过、1 跳过。SDK 55/6、Ruff/依赖检查通过。跳过的符号链接拒绝路径不记为通过。

软件证据根：`work/normalization-20261011/ccf9210a95624f7ba9401fbb79e0dead/`，含备份 bundle、来源快照、manifest、SDK/AST 对比和逐项结果。旧候选和原始失败日志保留。

原生证据根：`C:/Users/Public/Documents/MCP_HCL_Native_Test_20261011/c2f6bfc9fcb347d8a5b2f1d2f2fd0556`。原报告记录一次单设备隔离生命周期和 MCPHCLLab 删除；profile/工程/证据保留。旧候选 CLI 被后台 MultiCC 保护拒绝，命令未发送；配置/startup、重启与流量仍未验证。该记录不代表当前现场已重采，也不证明新候选原生通过。

## 下一步

先澄清 CLI 独占判定和执行身份，再准备必要专项。有效成功生命周期应复用，不重复启动，不自动重建旧账号。真实执行按 [测试指南](docs/live-acceptance.md)；参数、恢复与功能限制见 [合同](docs/contract-v2.md)。

固定上游目标为 61 工具/5 资源，库存仍为 12 implemented / 46 planned / 3 unverified。原生完整设备/线缆库存、若干 IOS 语义、clock_rate/EIGRP delay、旧 PVST/protect/restrict、原生命名 Exporter/monitor、完整审计规则和安全 Phone 关联等仍缺。

当前源码与历史分支已整合，来源工作区仍保留各自版本；E:/MCP_HCL 的旧 dsh-2 checkout 不是当前 main 源码。远端同步状态以 `git status --short --branch` 和实际 `origin/main` 为准。日期化报告和重复快照已移出仓库维护文档，仍可从 Git、原始证据和仓库外备份追溯。
