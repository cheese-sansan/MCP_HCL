# MCP_HCL HANDOFF

更新：2026-10-11（Asia/Tokyo）。本次用户明确授权 Codex 完成新增软件验证和合同内缺陷修复，随后授权在此处执行必要原生测试并删除实验账号。不得自动向其他模型/聊天派发任务。

**当前结论：软件验证及一次单设备隔离生命周期完成，CLI 阻塞，实验账号已删除；整体 Incomplete，full_live_gate_passed=false。** 当前源码及新 wheel 各执行同一受影响集合 177 项：176 通过、1 因符号链接权限不足跳过、0 失败/错误。不是两组独立用例的合计，也不是真实 HCL 验收。

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
2. 本轮单设备生命周期成功，复用具名证据，不重复启动证明同一事实。
3. 候选独占 CLI 被后台 MultiCC 检查拒绝，命令未发送；先修复/澄清保护和执行身份，再安排专项。配置与网络前提未满足，未扩大测试。
4. MCPHCLLab 已停用并删除；profile、工程及证据保留。未来真实专项必须另行准备身份与隔离环境，不自动重建旧账号。

原生全设备/线缆库存、完整实时编辑/模块/工作区/抓包、IOS ingress-role/池掩码数据面、clock_rate/EIGRP delay、旧 PVST/protect/restrict、原生命名 Exporter/monitor、完整审计规则和安全 Phone 原生关联保存/恢复仍缺。真实 CLI、配置/startup、流量/重启、认证明密文对应、BPDU/MAC 学习和 collector 收包仍未验证。

GUI 保护不证明 HCL/Wrapper 内部环境、GUI 实际后端连接或清理边界；保存文件不等于原生 canvas 库存。不要修改 BCD、安全功能、用户环境根、原厂镜像 UUID 或二进制，不自动重启，不终止他人的 PuTTY/MultiCC。

## 现场、账号和历史

最新现场为本轮单设备原生测试：正常启动、停止、保存、退出，原账号 52 文件、工程、注册清单未变。共享 boot/msr 镜像内容未变但 mtime 变化。候选 CLI 拒绝外部控制台占用，未发送命令，配置/网络未执行。没有提交、合并或 push。

MCPHCLLab 已按创建 SID/唯一标记停用并删除，profile 未删除。HCL 保存/退出自行清理 lab runtime/注册并归档配置盘，账号清理没有删除 VM/工程/证据。见 [本轮原生测试及清理报告](C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL/docs/native-test-and-cleanup-20261011.md)。证据根 `C:/Users/Public/Documents/MCP_HCL_Native_Test_20261011/c2f6bfc9fcb347d8a5b2f1d2f2fd0556`，完整验收仍未通过。

历史现场和恢复入口：[隔离记录](C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/docs/isolation-trial-execution-20261006.md)。本次修改前交接和测试指南已按原字节归档到各入口目录的 `docs/history/20261011-software-4589032f/`；更早历史未修改。
