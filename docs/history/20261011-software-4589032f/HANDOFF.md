# MCP_HCL HANDOFF

更新：2026-10-11（Asia/Tokyo）。这是当前工作入口；旧逐轮记录已按原字节归档到本目录的 docs/history/，历史失败与原回执没有改写。

## 目标和分工

完整复现固定上游 MCP-Packet-Tracer 的 61 工具/5 资源行为；不能以工具声明数或较小兼容子集替代完成目标。Codex负责软件与文档，测试由用户交给 DeepSeek Harness 中的 DeepSeek。不得自动向其他模型/聊天派发任务。用户要求只做必要测试、复用有效范围结果、保留失败。

**当前结论：Incomplete；full_live_gate_passed=false。** 本次只重写文档，没有测试、安装、启动HCL/guest、删除账号、提交、合并或push。

## 从哪里继续

| 定位 | 用途 |
|---|---|
| `C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL` | 当前软件源码，detached 9963ddc559d3f7d9ccecfc5a58f9adbaf2695f62，未提交改动 |
| `C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL` | 旧测试快照与真实失败/恢复证据；此次只改交接/测试指南，源码和测试未改 |
| `E:/MCP_HCL` | 旧dsh-2源码，HEAD e7231a3b4139219910af2bb84901aedd71bae986；当前软件未合入 |

本文件所在目录不一定是待测源码。先读 [统一测试计划](C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL/docs/live-acceptance.md)，按其中版本和层次接手，无需逐份追读旧临时增补。

固定候选：`C:/Users/Public/Documents/MCP_HCL_NetStream_Untested_20261007/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`3714fc784b95efd1fad1a05d3e9bfa6e39b0a46992132b0bb6c396d21f0e8328`。

2026-10-11只读复核：56包文件与当前软件源码匹配；Schema制品55工具/6资源。SDK发现/功能/原生验收不由此证明。旧editable venv指向8a46，测试时必须绑定正确导入路径或固定候选。不要重建候选后继续使用旧SHA/旧结论。

## 已有结果和新软件稿

历史238项软件回归与后续VLAN/ACL/NAT专项仅证明各自快照/范围，入口在统一测试计划。测试转交后的NAT事务、接口调优、STP/端口安全、差异/健康/IPv6、GUI身份保护、安全审计和NetStream尚无本次纳入的功能/原生验收结果。

当前库存记账为12 implemented/46 planned/3 unverified；上游固定revision为846db381bc2c6ee0229d56e1d7ce8847eb6b213d。55声明不是55通过，更不是完整61/5等价。详细合同保留在当前源码的docs/；统一测试计划索引每组必要用例。

## 下一步顺序

1. DeepSeek先固定候选/源码SHA和导入路径，补齐新增关键用例、检查SDK发现与默认门控；受影响范围之外复用旧证据。
2. 接手前只读复核当前实验SID、profile、进程、运行时与原资产；2026-10-06现场观察已过期，不能当作当前状态。
3. 进行一次尚缺的单设备隔离生命周期，再验证独占CLI；通过后才推进必要配置/网络用例。已有成功启动不重复；阶段工程副本不是VM目录隔离证明。
4. 将实际结果绑定版本/证据并更新交接。功能未实现记NotImplemented；读取或证据不足记Unverified，不调试成“模拟通过”。
5. 全部必要真实测试结束后清理临时账号；保留数据与证据。

## 仍未完成的软件与真实门槛

原生全设备/线缆清单和完整实时编辑/模块/工作区/抓包；IOS/HCL配置语义的若干映射；命名Exporter/monitor与独立设置；完整审计规则；安全Phone关联保存/恢复等仍缺。GUI保护只观察调用者目录和进程/默认监听者，不证明HCL/Wrapper内部环境、GUI实际后端连接或清理边界；保存文件不是已验证原生canvas清单。

真实CLI权限/占用、生命周期隔离、配置/startup、流量/重启和有线/无线整体验收仍未通过。不要修改BCD、安全功能、用户环境根、原厂镜像UUID或二进制，不自动重启，也不终止他人的PuTTY/MultiCC。

## 现场与账号

最后现场证据日期为2026-10-06：错误UAC身份曾让主账号资产再次被清理，已恢复缺失47文件和原Base注册；新普通客户端尝试未打开工程/启动guest，控制器和观察器期限失败保留。该日收尾记录无相关运行进程/profile未加载，本次没有重采机器状态。

MCPHCLLab是临时标准测试账号；创建SID/唯一标记以 [创建回执](C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/work/account-creation-20261005/748abd1c1434409d8b9ab95e0f37c68c/account-receipts/3a42945c83794fcabde4763c5def3e8c/result.json) 为准，勿仅按账号名称行动。用户已授权全部必要真实测试后停用并按SID删除，不重复索取同一授权；保留profile、VM、日志和证据。账号当前状态须接手复核，本次未删除。凭据不写入文档/argv/环境/回执。

历史实测和恢复入口在 [隔离记录](C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/docs/isolation-trial-execution-20261006.md)。当前候选的 [交付记录](C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL/docs/netstream-delivery-20261007.json) 明确只有构建/字节范围；旧临时handoff均为历史快照，不再作为最新入口。

## Suggested skills

api-and-interface-design：严格参数与分层证据合同；tool-failure-handling：独占、超时、幂等、失败与恢复；computer-use:computer-use：只在必要真实GUI验收时使用；handoff：根据实际结果更新入口。技能建议不增加授权范围。
