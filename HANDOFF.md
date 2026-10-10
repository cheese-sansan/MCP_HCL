# MCP_HCL HANDOFF

更新：2026-10-11（Asia/Tokyo）。本轮按用户授权完成全部本地分支历史整合、最新未提交成果纳入和代码规范化。原生结论仍为 **Incomplete；full_live_gate_passed=false**。

## 当前入口

当前整合源码：`C:/Users/w8p1p/.codex/worktrees/ddea/MCP_HCL`。本地主分支 `main` 纳入 `codex/hcl-live-parity`、`dsh-2` 和 `nat-transactions` 的已验证工作区成果。来源分支及工作区保留，不删除、不覆盖；没有 push。

读 [规范化报告](docs/normalization-20261011.md)、[文档索引](docs/README.md) 和 [统一测试计划](docs/live-acceptance.md)。旧工作区不是规范化源码位置：E:/MCP_HCL 仍是 dsh-2 历史 checkout；8a46/ed66/nat-transactions 原文件与 HEAD 保持。

新规范化候选：`C:/Users/Public/Documents/MCP_HCL_Normalized_20261011_ccf9210a/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`2c57afcdf7b0f5234a738a255c5b904e15d52a000e6ab7f5f6aacd6af9e5880a`。57 个包文件与当前源码逐字节一致；此前 56 文件、SHA `3d3663ca…65f9a` 的候选及回执保留，属于重构前版本。

## 软件验证

整合基线与规范化源码各执行完整 330 项软件回归：329 通过、1 项符号链接权限跳过、0 失败/错误。Ruff lint/format 通过。完整 SDK 声明与重构前逐项相同：55 工具/6 资源，参数、默认值、错误和门控合同保持。

`transactions.py` 收纳交换预算、原子 JSON、幂等历史读取和未验证结果。助手主体保持原 AST，NAT 保留兼容导出；各功能自己的命令、备份、回读与恢复顺序没有重写。

所有软件会话真实写开关为 0。默认检查入口为 `scripts/check_all.py`，每轮生成新回执。共用 Windows API/PowerShell 软件测试使用合成 pipe、Plan/ValidateOnly、解析或退役拒绝，不启动 HCL/guest、不进行账号或宿主修改。

证据根：`C:/Users/w8p1p/.codex/worktrees/ddea/MCP_HCL/work/normalization-20261011/ccf9210a95624f7ba9401fbb79e0dead`。包含 all-refs.bundle、全部来源 tracked/untracked 文件快照、逐文件 SHA、完整回归、SDK 前后声明、AST 检查、来源工作区/历史文件保留验证和新候选记录。历史测试日志及 JSON 不改写。

## 原生事实与后续

2026-10-11 的 [单设备测试和清理报告](docs/native-test-and-cleanup-20261011.md) 记录一次单设备隔离生命周期、原资产范围检查及 MCPHCLLab 账号删除，profile/工程/证据保留。候选 CLI 被后台 MultiCC 保护拒绝，命令未发送。复用该轮成功生命周期，不重复启动，也不自动重建旧账号。

本轮规范化没有启动 HCL/guest、访问真实控制台、原生配置/流量测试、删除账号或修改宿主设置。真实 CLI、配置/startup/重启、认证明密文对应、BPDU/MAC 学习、collector 收包和正式有线/无线仍未通过。

原生全设备/线缆库存、若干 IOS→Comware 行为、clock_rate/EIGRP delay、旧 PVST/protect/restrict、原生命名 Exporter/monitor、完整审计规则和安全 Phone 关联等仍缺；测试不能把缺口补成通过。固定上游 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d` 的 61 工具/5 资源目标不变，库存仍为 12 implemented / 46 planned / 3 unverified。

不要修改 BCD、安全功能、用户环境根、原厂镜像 UUID/二进制，不自动重启，不终止他人的 PuTTY/MultiCC。先澄清 CLI 独占保护和执行身份，再准备必要真实专项；用户授权不扩大到发布或来源分支删除。
