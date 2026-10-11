# MCP_HCL 当前交接

当前源码位于 `C:/Users/w8p1p/.codex/worktrees/ddea/MCP_HCL` 的 main，版本 0.5.0，完整交付仍 **Incomplete**，`full_live_gate_passed=false`。使用入口见 [README](README.md)，维护文档见 [docs/README](docs/README.md)。

## 当前版本与证据

当前候选：`C:/Users/Public/Documents/MCP_HCL_API_Contracts_20261012_5e8578f9/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`2213e9c3e81e4d9e26e2ad6a22c3b4e41412ecc88f613bb59b3337686e56849f`。59 个包文件与当前源码及候选安装副本逐字节一致。本机完整软件检查 346 项、345 通过、1 符号链接权限跳过；候选 SDK/协议/API 对应专项 40 项、39 通过、1 跳过。HCL 声明面 55/6，复现基线 62/5。没有对应权限的跳过路径不记为本机通过。

前一候选 `7a74d260…9c9` 及其提交 2f7ec0f 的云端 338 项结果保留；它不包含当前 API 对照增量，不能冒充新源码或候选的结果。当前 CI 状态须按实际提交检查。

旧规范化候选 `2c57afcd…5880a` 和首轮 `b52e247c…56812` 及其结果保留，不能标识修复后的当前源码。

软件证据根：`work/normalization-20261011/ccf9210a95624f7ba9401fbb79e0dead/`，含备份 bundle、来源快照、manifest、SDK/AST 对比和逐项结果。旧候选和原始失败日志保留。

原生证据根：`C:/Users/Public/Documents/MCP_HCL_Native_Test_20261011/c2f6bfc9fcb347d8a5b2f1d2f2fd0556`。原报告记录一次单设备隔离生命周期和 MCPHCLLab 删除；profile/工程/证据保留。旧候选 CLI 被后台 MultiCC 保护拒绝，命令未发送；配置/startup、重启与流量仍未验证。该记录不代表当前现场已重采，也不证明新候选原生通过。

## 下一步

真实 CLI 仍需验证内核独占检查及执行身份，再准备必要专项。用户已确认普通账号与隔离工程暂未准备；软件工作继续，原生专项保持 Unverified。有效成功生命周期应复用，不重复启动，不自动重建旧账号。真实执行按 [测试指南](docs/live-acceptance.md)；参数、恢复与功能限制见 [合同](docs/contract-v2.md)。

复现目标已扩展并固定到上游 `3c7c7a46b9ea27c914f845d161f95f0fc3f53d5f` 的 62 工具/5 资源，库存为 12 implemented / 47 planned / 3 unverified，HCL 声明面仍为 55/6。原生完整设备/线缆库存、若干 IOS 语义、clock_rate/EIGRP delay、旧 PVST/protect/restrict、原生命名 Exporter/monitor、完整审计规则和安全 Phone 关联等仍缺。

当前源码与历史分支已整合，来源工作区仍保留各自版本；E:/MCP_HCL 的旧 dsh-2 checkout 不是当前 main 源码。远端同步状态以 `git status --short --branch` 和实际 `origin/main` 为准。日期化报告和重复快照已移出仓库维护文档，仍可从 Git、原始证据和仓库外备份追溯。

## 完整复现目标与推进顺序

hcl_parity_report 的 reproduction_targets 保存以下全部目标、依赖和验收条件；不能以接口声明或软件测试把它们标为完成。

| 目标 | 关闭条件 | 当前层次 |
|---|---|---|
| 独占 CLI | 单连接证据、服务器身份/VM/配置盘绑定、真实回显/提示符，忙/未知路径拒绝 | 内核检查已实现；真实 HCL 待验 |
| 完整原生库存 | 全设备、线缆、端口与非 VM 终端的权威清单和稳定归因 | planned |
| 实时编辑/生命周期 | 创建、删除、改名、移动、链接、端口、模块与注释均原生前后回读，统一隔离保护 | planned |
| 有线完整闭环 | 规划→创建/连线→启动→配置→DHCP/OSPF/ping→保存/恢复，无手工复制配置 | CLI/库存前提未满足 |
| 配置行为等价 | NAT ingress/池掩码、clock/delay/EIGRP、STP/BPDU/MAC、认证与原生命名 NetFlow 等语义，以及 native startup/恢复/重启 | partial |
| 安全无线闭环 | AC/AP/交换机/2 Phone，真实 WPA2-PSK、租约、双向 ping、保存/恢复 | blocked |
| 完整实时观察 | 原生 diff/health、端口/VLAN/QoS/IPv4/IPv6/路由域与完整覆盖 | partial |
| 模拟/抓包/工作区 | HCL 可验证的逐事件/逐层等价、截图、项目元数据与工作区设置；普通抓包不替代完整事件合同 | planned |
| 独立 DHCP Server | 明确服务器角色的池读/创建/更新/删除、默认值/范围/DNS/网关、原生回读和实际租约 | planned；不注册占位工具 |
| API 对应 | 62/5 的名称、参数、默认值、错误、结果和能力协商明确对应，不静默缩小范围 | 声明/当前 Schema 对照已实现；转换及行为等价未完成 |
| 交付与证据 | 精确候选的全部必要原生验收、可复现安装与软件/发布检查、分层证据 | blocked |

本轮首先取消 CLI 对任意后台 MultiCC 的一刀切占用结论，改为连接后的内核单实例证据；共享文件锁、原生忙/权限错误、回显、预算、服务器身份与原 UUID 恢复保护保留。多/无限实例和未知信息不发送。Windows 私有合成管道证明软件路径，不证明 VirtualBox/HCL 已接受。

接手只读复核未观察到旧实验账号及运行 Client/Wrapper/MultiCC/guest；本轮不重建账号、不启动 HCL/guest。后续真实 CLI 专项需要已审阅的普通身份/隔离工程。先关闭该前提及原生库存，再推进有线闭环；其余目标继续保留。

本轮源码/测试基线和新回执根：`work/reproduction-62-20261011/018ef18892ed4024a273473dcefef4b6/`。原失败与旧候选不覆盖。

软件交付检查已加入 `.github/workflows/software-ci.yml`：Windows/Python 3.12、默认写开关 0、完整软件检查、wheel 构建及独立日志制品。CI 是软件门槛，不替代原生验收；实际运行状态以对应提交的 Actions 结果为准。

云端干净环境暴露的 Windows 8.3 路径别名误判已修复：证据模板比较解析后的同一文件，路径/哈希/链接保护保留；NetStream 故障注入明确命中规范化目标。首轮失败回执和原工作副本换行字节保存在本轮 work 目录。当前数据文件与 Git/CI 的正式字节对齐，避免旧工作区换行差异混用候选。

## 当前软件增量

2026-10-12 增加 `hcl_parity_report.api_compatibility`，覆盖上游 62/5 固定声明和当前 55/6 MCP 发现结果。逐工具列出参数、必填性、默认值、返回注解、实际 HCL 输入 Schema 和未实现目标；`request`/`parameters` 的同名候选不表示可执行转换。所有输出/错误/行为等价仍为 unverified，自动转换仍 false；上游 `pt_*` 不注册占位别名。API 目标推进到 partial，不提升原生字段或 12/47/3 库存计数。

同时修正库存中“未测试/等待外部测试”的旧描述，明确 NAT、接口、交换机安全、NetStream、观察/审计及 GUI 的软件测试层与原生未验证层。

基线、源码/依赖清单、逐项测试、API 对照快照和新候选身份位于 `work/api-contracts-20261012/5e8578f9bf144f489deb1433ea9733f3/`。旧失败、历史候选及原生证据保留。下一软件目标继续处理配置语义及原生库存的可验证来源；真实调用等待已准备的普通身份/隔离工程。
