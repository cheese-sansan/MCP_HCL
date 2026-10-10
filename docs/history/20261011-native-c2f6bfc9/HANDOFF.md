# MCP_HCL HANDOFF

更新：2026-10-11（Asia/Tokyo）。本次用户明确授权 Codex 完成新增软件验证和合同内缺陷修复；原生验收继续由用户交给 DeepSeek Harness 中的 DeepSeek。不得自动向其他模型/聊天派发任务。

**当前结论：软件验证完成，整体 Incomplete；full_live_gate_passed=false。** 当前源码及新 wheel 各执行同一受影响集合 177 项：176 通过、1 因符号链接权限不足跳过、0 失败/错误。不是两组独立用例的合计，也不是真实 HCL 验收。

## 版本和入口

| 定位 | 用途 |
|---|---|
| `C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL` | 当前源码；detached `9963ddc559d3f7d9ccecfc5a58f9adbaf2695f62`，原有及本次改动未提交，版本由逐文件 SHA 清单固定 |
| `C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL` | 历史快照与真实失败/恢复证据；本次未修改其源码或测试 |
| `E:/MCP_HCL` | 旧 dsh-2 源码，HEAD `e7231a3b4139219910af2bb84901aedd71bae986`；当前软件未合入，仅同步交接/测试入口 |

本文件所在目录不一定是待测源码。先读 [软件验证报告](C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL/docs/software-verification-20261011.md) 和 [统一测试计划](C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL/docs/live-acceptance.md)。

新固定候选：`C:/Users/Public/Documents/MCP_HCL_Software_Verified_20261011_4589032f/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`3d3663ca1c65ffc9c93b5281a460469de3a0d1f39115307704e9775f33465f9a`。

56 个包文件与当前源码逐字节一致，SDK 发现 55 工具/6 资源；新 venv 安装候选后验证实际 site-packages 导入，依赖检查通过。旧 `MCP_HCL_NetStream_Untested_20261007` 候选、SHA 和历史结论保留，不用于标识新候选。

## 软件结果和修复

NAT、接口调优、STP/端口安全、差异/健康/地址、GUI 身份、安全审计和 NetStream 的具名软件合同及模拟失败恢复已执行。旧工具断言和 GUI 夹具适配完成；修复不支持交换安全请求的前置无 I/O、线路凭据漏读、密钥紧贴异常文本漏遮蔽、损坏幂等历史未封装四类实现缺陷。完整覆盖矩阵、依赖、日志和 manifest 在软件验证报告及其 JSON 中。

证据根：`work/software-verification-20261011/4589032fc5584d0b8cfedfa7c6cbee41/`。源码最终回执在 `runs/c648afa0515e4c62a17756b70275c543/`；候选最终回执在 `candidate-runs/5a2a6356c48e42d09bd2c54a350d14e8/`。全部中间失败和原 68 项失败日志保留。父进程/SDK 子进程保持 `MCP_HCL_ALLOW_LIVE_WRITE=0`；模拟来源不提升原生字段。

历史 238 项回归及 VLAN/ACL/NAT 专项仍仅证明原各自版本/范围，旧交付 JSON 不改写。固定上游 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d` 的目标仍为 61 工具/5 资源，库存仍为 12 implemented / 46 planned / 3 unverified。55 工具发现不等于完整功能或上游行为等价。

## 下一步和未决项

1. 无新软件改动时复用本次范围结果；换候选或源码变化时先核对 SHA/导入来源，再定向复测。
2. 原生接手先只读复核实验 SID/profile、进程/监听者、运行时根/注册和原资产；2026-10-06 现场记录已过期。
3. 进行一次尚缺的单设备隔离生命周期，再验证独占 CLI；通过后才推进必要配置/网络用例。已有成功启动不重复，阶段工程副本不是 VM 目录隔离证明。
4. 未实现能力记 NotImplemented，原生证据不足记 Unverified。全部必要真实测试结束后才进行已授权账号清理。

原生全设备/线缆库存、完整实时编辑/模块/工作区/抓包、IOS ingress-role/池掩码数据面、clock_rate/EIGRP delay、旧 PVST/protect/restrict、原生命名 Exporter/monitor、完整审计规则和安全 Phone 原生关联保存/恢复仍缺。真实 CLI、生命周期隔离、配置/startup、流量/重启、认证明密文对应、BPDU/MAC 学习和 collector 收包仍未验证。

GUI 保护不证明 HCL/Wrapper 内部环境、GUI 实际后端连接或清理边界；保存文件不等于原生 canvas 库存。不要修改 BCD、安全功能、用户环境根、原厂镜像 UUID 或二进制，不自动重启，不终止他人的 PuTTY/MultiCC。

## 现场、账号和历史

本次没有启动 HCL/guest、原生配置写入、流量测试、账号删除、提交、合并或 push，也没有重采账号/原资产状态。最后现场证据仍为 2026-10-06：错误 UAC 身份曾造成原资产清理，缺失 47 文件及原 Base 注册按旧回执恢复；普通客户端控制器/观察器失败保留。

MCPHCLLab 的身份以 [原创建回执](C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/work/account-creation-20261005/748abd1c1434409d8b9ab95e0f37c68c/account-receipts/3a42945c83794fcabde4763c5def3e8c/result.json) 为准，不仅按名称行动。用户已授权全部必要真实测试完成后按创建 SID/唯一标记停用并删除账号；保留 profile、VM、日志及证据。清理条件未满足，账号未删除，凭据不写入文档/argv/环境/回执。

历史现场和恢复入口：[隔离记录](C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/docs/isolation-trial-execution-20261006.md)。本次修改前交接和测试指南已按原字节归档到各入口目录的 `docs/history/20261011-software-4589032f/`；更早历史未修改。
