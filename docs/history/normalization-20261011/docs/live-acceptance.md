# MCP_HCL 测试计划

更新：2026-10-11（Asia/Tokyo）。本次软件验证和缺陷修复由用户明确授权 Codex 执行；随后用户授权 Codex 在此处执行必要原生测试并删除实验账号。源码和新 wheel 各 177 项：176 通过、1 权限跳过、0 失败/错误。本轮单设备隔离生命周期完成，CLI 阻塞；MCPHCLLab 已删除，profile/工程/证据保留。见 [本轮报告](native-test-and-cleanup-20261011.md)。

## 1. 固定待测版本

| 项目 | 权威定位 |
|---|---|
| 当前软件源码 | `C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL` |
| 源码基线 | detached `9963ddc559d3f7d9ccecfc5a58f9adbaf2695f62`；大量未提交改动，HEAD 不能单独确定版本 |
| 固定候选 | `C:/Users/Public/Documents/MCP_HCL_Software_Verified_20261011_4589032f/mcp_hcl-0.5.0-py3-none-any.whl` |
| wheel SHA256 | `3d3663ca1c65ffc9c93b5281a460469de3a0d1f39115307704e9775f33465f9a` |
| 声明/Schema 制品 | 55 工具、6 资源；源码及候选 SDK 发现已验证 |
| 固定上游 | `846db381bc2c6ee0229d56e1d7ce8847eb6b213d`，61 工具、5 资源 |

2026-10-11 本轮：新候选 56 个包文件与当前源码逐字节一致，源码/候选的软件合同、模拟事务和 SDK 验证均已执行，证据见 [软件验证报告](C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL/docs/software-verification-20261011.md)。旧候选及其历史 SHA 保留；本次软件结果不证明原生行为。旧 8a46 是历史测试/实测回执所在工作区；E:/MCP_HCL 的 dsh-2 是旧源码，不能用它评价本候选。旧版本 0.5.0 的版本号也不能代替 SHA。

本指南所在目录可能是入口副本。所有待测代码均以上表的软件源码或固定候选为准。

## 2. 结果如何复用

- 历史完整软件回归：238 项、237 通过、1 跳过；对应旧快照，见软件源码 `docs/acl-persistence-verification-20261006.json`。不是最新候选的完整回归。
- 后续 VLAN/ACL 删除/NAT 生成专项分别见 `docs/vlan-network-verification-20261006.json`、`docs/acl-removal-verification-20261006.json`、`docs/nat-modes-verification-20261006.json`。仅在版本/代码路径/范围匹配时复用。
- 新增 NAT 事务、接口调优、交换安全、差异/健康、地址观察、GUI 保护、安全审计与 NetStream：本次软件合同和模拟功能验证完成，具名用例及失败历史见软件验证报告。固件、原生配置和数据面验证仍未完成。
- 不重复旧成功 guest 启动，不无理由重跑整个历史回归。新增代码、失败或未决要求涉及的用例才执行；共享备份/恢复/幂等检查能覆盖多个功能时合并执行。
- 每次失败保留，新操作使用新 operation_id/目录。不得覆盖失败回执、改写原结果或将未知记为通过。本次纳入 Codex 明确授权的软件结果，没有纳入新的 DeepSeek 原生结果；接手方的其他结果须先绑定源码/候选 SHA。

## 3. 软件验证：先完成这层，再安排真实操作

在新的软件验证会话保持 `MCP_HCL_ALLOW_LIVE_WRITE=0`。使用隔离 Python 3.11+ 环境和项目依赖。8a46 的既有 venv 是旧源码 editable 安装；接手时验证实际 `mcp_hcl.__file__`，或明确设置当前源码 `src` 的 PYTHONPATH，不能混用包与源码。

第一组：核对 SDK 发现 55 工具/6 资源、严格 JSON 类型、未知字段、参数 Schema、默认门控、错误封装。现有 `tests/test_mcp_contract.py`、`test_stdio.py`、`test_parity.py` 是入口，旧数量断言已维护为独立的明确名称清单；只改数量不能证明功能。本次九个新增工具的 Schema/合法调用/门控/错误封装已专项验证。

第二组：下表新增功能的软件专项已补齐并执行，逐项结果见软件验证报告及 JSON。下表继续作为合同索引，未来变更仅执行受影响范围。

| 功能 | 必要检查 | 实现/合同入口（当前软件源码的 docs/） |
|---|---|---|
| 共用事务 | 真实/模拟来源分离、绑定 UUID/配置盘/管道、独占、预算、备份/startup、保存/回执失败、恢复原 UUID、幂等键不重放 | acl-persistence-20261006.md、nat-transactions-20261006.md |
| NAT | static/dynamic/PAT、池/ACL 身份、共享引用、任意 wildcard、精确删除 | nat-transactions-20261006.md |
| 接口调优 | 指定标量范围、OSPF 计时器/默认值、认证模式/多 key、明文/编码/历史遮蔽、unsupported 字段整次无 I/O | interface-tuning-20261006.md |
| STP/端口安全 | VLAN 范围、root/priority、全局 BPDU 影响、认证重置、动态/sticky/MAC 状态保护、拒绝路径 | switch-security-20261007.md |
| 差异/健康/地址 | 字段未知、缺设备/线缆、主/辅助/IPv6/链路本地、DAD/anycast、VPN 列/别名、阶段变化，禁止伪同步/健康通过 | reconciliation-20261007.md、address-observation-20261007.md |
| GUI 打开/保存 | SID/非提权/进程/监听者、调用者目录、既有资产拒绝、内存许可、账号共享锁、动作端复核、超时、模拟回执 | gui-identity-20261007.md |
| 安全审计 | 跨行 banner 伪命令、存储模式、未知算法/RBAC/AAA；成功和失败返回/文件不得有密码、密文、raw 控制台或配置哈希 | security-audit-20261007.md |
| NetStream | 名字/VM/模拟元数据、共享版本/源接口、精确地址/端口/公共域、聚合拒绝、保存/元数据失败/恢复 | netstream-transactions-20261007.md |

上述软件层已由 Codex 按本次明确授权执行，后续原生检查须先解决本轮 CLI 阻塞并准备新的隔离身份；模拟通过不提升原生结论。配置、原始回读、PSK、截图与备份放私有目录，不放入 Git/候选包或发送到外部。

## 4. 未实现与未验证必须分开

以下缺口不能靠重复测试闭合：原生全设备/线缆库存；完整实时编辑/模块/工作区/抓包能力；IOS ingress-role/池 mask 数据面映射；clock_rate/EIGRP delay；旧 PVST/root-primary 动态算法/protect/restrict；原生命名 Exporter/monitor 与独立设置；完整 Cisco→Comware 审计规则；安全 Phone 关联的原生保存/恢复等。按各合同中的拒绝/unknown 行为检查，记录为 NotImplemented 或 Unverified，继续软件实现后再测。

库存记账仍为 12 implemented / 46 planned / 3 unverified；接口数量不是完成率。`full_live_gate_passed=false`。配置回读、合成测试、VM RUNNING、绿色图标或保存文件均不能替代真实 CLI、流量、隔离或完整行为等价。

## 5. 真实验收前提与顺序

### 5.1 接手现场复核（只读，避免沿用过期状态）

历史方案使用 MCPHCLLab 普通账号；该账号已在本轮结束后删除。以下为历史前提及未来验收约束，不能直接复用该账号。真实 SID、CIM profile、USERPROFILE/AppData/Temp、HCL/Wrapper/VBoxSVC 所有者、监听者、运行时根/注册及原资产基线必须核对；不手工覆盖用户环境根制造通过。不要重新创建账号，也不要把主账号的注册、HCL VMs 或 gen_py 搬入实验账号。

最新现场是本轮 2026-10-11 原生测试及账号清理报告；2026-10-06 记录保留为历史。本轮 HCL/Wrapper/MultiCC/guest 正常退出，profile 未加载，原账号资产不变；实验 VBoxSVC 后台进程仍被观察到。证据入口见 8a46 `docs/isolation-trial-execution-20261006.md`。

已记录：H3C Cloud Lab.exe 要求管理员权限；错误 UAC 身份曾引发原资产清理。SimwareClient.exe 是现有 asInvoker 入口，曾取得实验 SID 的进程证明，**不代表完整生命周期已通过**。若出现 UAC/身份变化，停止自动操作，不输入管理员凭据，不修改 manifest、安全功能或 BCD，不自动重启。

### 5.2 一次必要单设备隔离验收

本轮已完成以下单台 MSR36-20 生命周期；不得无理由重复。历史范围：打开→创建→启动→正常停止→退出一次。旧输入：`C:/Users/MCPHCLLab/Documents/HCL_Trials/Isolation_c9ca01c8/v7_sw_vlan_basic/v7_sw_vlan_basic.net`；实际路径、可读性和工程内容由接手复核，缺失不能重新构造为旧证据。

记录实际 SID/运行时根/注册、VM UUID/CfgFile/配置盘/父盘/UART，保护原账号 52 文件与 Base 注册。单独的 .net/workingdir 不算隔离。前后差异或身份错误时停止后续验收，按既有恢复回执处理，不清空目录、覆盖已有文件或修改原镜像 UUID。

本轮补齐隔离生命周期，候选独占 CLI 被后台 MultiCC 保护拒绝、命令未发送。后续只安排解决阻塞后的 CLI 专项，不能重复本轮生命周期证明同一事实。占用、拒绝、截断、超时必须保留；不得终止别人的 PuTTY/MultiCC。

### 5.3 配置/网络与完整交付门槛

前两层通过且相关软件缺口补齐后，再按整体交付范围运行必要配置/网络用例。配置写入必须先备份并验证恢复入口，失败按原 UUID 恢复，运行配置、startup 指针/内容、流量与重启结论分别报告。

原有正式有线要求保留：3 MSR36-20、3 S5820V2-54QS-GE、每 LAN 2 PC DHCP；三路由器线性 /30，LAN /24，OSPF 1/area 0；4 条方向 FULL 邻居、远端 LAN 路由、6 唯一租约/网关、LAN 两两双向各 5 包零丢包。

原有无线要求保留：1 AC、1 AP、1 交换机、2 Phone，管理 VLAN 1/业务 VLAN 10，真实 WPA2-PSK、2 唯一租约和双向各 5 包零丢包。安全 Phone 原生关联/持久化/恢复仍缺时停止于该门槛，不能以开放 Wi-Fi、有线替代或 AP CLI 模拟通过。不要把未来完整门槛一次性当作立即执行的扩大测试任务。

## 6. 交付结果与账号清理

每组回执至少记录：源码/候选 SHA、环境/执行方、operation_id、已执行用例及 Passed/Failed/Unverified/NotImplemented/Skipped、对应证据路径、实际修改与恢复结果、未决项、原资产前后状态。声明/Schema、协议、原生配置、隔离和流量分层报告。没有相应证据的字段保持 false/unknown。

**当前清理状态：MCPHCLLab 已按本轮测试结束后的用户指令停用并删除。** CLI 保护拒绝后本轮停止，配置/网络未运行，完整产品验收仍 Incomplete。profile、工程、配置盘归档和证据保留；HCL 退出自行清理 lab 临时 runtime。以下清理命令作为历史过程参考，不再执行。

使用原创建回执及审阅脚本，先确认 SID/唯一 description、实验账号已注销/profile 未加载。脚本须在原 owner 的管理员 PowerShell 中运行；不向 HCL 的 UAC 提示输入管理凭据：

```powershell
$mcpAccountScript = 'C:\Users\w8p1p\.codex\worktrees\8a46\MCP_HCL\scripts\hcl_lab_account.ps1'
$mcpCreationReceipt = 'C:\Users\w8p1p\.codex\worktrees\8a46\MCP_HCL\work\account-creation-20261005\748abd1c1434409d8b9ab95e0f37c68c\account-receipts\3a42945c83794fcabde4763c5def3e8c\result.json'
& $mcpAccountScript -Action Disable -RecordFile $mcpCreationReceipt
& $mcpAccountScript -Action Remove -RecordFile $mcpCreationReceipt
```

本轮两条命令已执行并取得 verified 回执，见本轮报告；不得再次对同名账号执行旧清理。每步查看新回执后再继续，核对账号 SID 消失、profile/VM/证据仍保留。脚本发现 HCL/console/guest 进程会拒绝，可能包括他人的会话；不得终止他人进程或绕过检查。状态不匹配/未知时保留账号并记录阻塞。

## 7. 历史证据入口

以下实测路径以 `C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL` 为根：

- `docs/isolation-trial-execution-20261006.md`、`docs/isolation-trial-review-20261006.md`：范围、失败、时间界限及准备工程。
- `work/isolation-lifecycle-20261006/f37f1f638a9f419ea395225670f42951/restoration-verification.json`：错误管理员身份退出后的恢复。
- `work/isolation-lifecycle-20261006/c9ca01c8a6cd44cd912821143860d320/handoff-state.json`、`handoff-main-assets.json`：最后收尾观察；不是最新现场状态。
- `docs/account-creation-20261005.md`、`docs/lab-account-review-20261005.md`、上述创建回执：身份与账号回退规则。
- `E:/MCP_HCL/work/feasibility/plan-b-20261002/backup-receipt.json`：原 52 文件备份定位。旧失败与恢复不得覆盖。

work/ 被 Git 忽略，换机器/工作区须核实证据可读性。缺失、权限拒绝、进程消失或观察器期限到均不能补写成通过。
