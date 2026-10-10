# MCP_HCL 新增软件验证与缺陷修复

2026-10-11，Asia/Tokyo。执行方：Codex，依据用户本次明确授权。软件层验证完成；整体交付仍为 **Incomplete**，`full_live_gate_passed=false`。

## 版本与结果

源码：`C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL`，HEAD `9963ddc559d3f7d9ccecfc5a58f9adbaf2695f62`，存在原有及本次未提交改动。HEAD 不单独标识待测版本，以逐文件 SHA 清单为准。

新候选：`C:/Users/Public/Documents/MCP_HCL_Software_Verified_20261011_4589032f/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`3d3663ca1c65ffc9c93b5281a460469de3a0d1f39115307704e9775f33465f9a`。56 个包文件与源码逐字节一致，没有缺失文件。旧 `3714fc78…e8328` 候选未覆盖。

| 验证对象 | 执行 | 通过 | 失败/错误 | 跳过 |
|---|---:|---:|---:|---:|
| 当前源码 | 177 | 176 | 0 / 0 | 1 |
| 独立环境安装的新 wheel | 177 | 176 | 0 / 0 | 1 |

两组是同一受影响测试集合在不同导入来源上的验证，不合计成 354 个独立用例。均确认 SDK 发现 55 工具/6 资源；固定上游 61/5 与 12 implemented / 46 planned / 3 unverified 的记账没有提升。

跳过项：`test_symlinked_project_json_is_rejected`，当前账号不能创建符号链接。该真实文件系统拒绝路径尚无本次通过证据。

Python 3.12.14；运行依赖从既有环境提取版本并在新 venv 精确安装，完整版本清单随回执保存。构建使用独立 venv 的 setuptools 84.0.0 和独立源码副本；`pip check` 通过。

## 修复与覆盖

旧的 46 工具断言改为独立明确列出的 55 工具合同清单，覆盖发现测试、stdio、ACL 删除、VLAN 网络及离线入口。上游数量与完成状态仍单独断言。

GUI 夹具同时注入采集和动作依赖，适配 inline PowerShell 常量参数，并包含 actor 的 `process_identity` 检查。模拟成功是 `output_received`，`project_identity_verified=false`、`protocol_project_identity_verified=true`；不修改生产身份保护以迁就旧测试。

本次修复四类实现缺陷：

- STP 旧 PVST、端口安全 protect/restrict 和超出当前支持容量的请求，在阶段读取、管道打开和备份之前整次返回 unverified。
- 安全审计识别线路的 `set authentication password` 形式；本机命令帮助 `D:/HCL/CMD-help/-129396861/-578369585/-768115199.htm` 支持该命令，密码值不进入报告。
- 接口认证错误、命令及输出文本中，密钥紧贴其他字符时仍遮蔽；保留状态枚举及身份字段的原有处理，不导出 raw base64 或相关请求/输出哈希。
- NAT、接口调优、交换安全和 NetStream 的缺失/损坏/非对象历史回执，返回关联原操作的明确未验证结果；同键不重放，冲突仍拒绝，旧历史不被改写。

| 合同组 | 具名测试入口及覆盖 |
|---|---|
| SDK | `test_new_sdk`：九个新增工具发现、Schema、合法门控调用、外层/嵌套类型与未知字段、缺字段、离线预览和错误封装 |
| 共用事务 | `test_transaction_failures`：绑定/管道/占用、备份、startup 内容与未知指针、预算、范围变化、恢复 UUID、关闭/回执错误、幂等冲突与损坏历史；`test_acl_persistence` 复核共用恢复语义 |
| NAT | `test_nat_transactions`、`test_nat_modes`：三种模式与两种 PAT 事务、网络表达、ACL 映射/来源、池分段/漂移、共享引用、精确删除与元数据命名空间 |
| 接口调优 | `test_interface_tuning`：严格范围、计时器/固定默认、未知默认拒绝、认证模式及多 key、partial 边界、成功/失败遮蔽、不支持字段无 I/O |
| STP/端口安全 | `test_switch_security`：VLAN 区间、root/priority 顺序、全局 BPDU 影响、edge 冲突、认证重置、动态/sticky 与 MAC、整次拒绝和恢复 |
| 差异/健康/地址 | `test_reconciliation`、`test_address_observation`：IPv4 主/辅助/缺失字段、IPv6 按需读取、DAD/ANYCAST/生命周期、链路本地、VPN/别名/二次变化、部分失败和阶段变化；健康/完整库存保持未知 |
| GUI | `test_gui_identity`、`test_gui_relay`：SID/令牌/会话/创建时间、进程及监听者路径/哈希、目录与资产、许可与共享锁、动作参数绑定、超时不重放、错误/缺失回执和模拟来源 |
| 安全审计 | `test_security_audit`：banner 伪命令、完整性、新旧用户/线路、存储分类与未知算法、规则排序、PC 排除、部分失败、阶段变化及所有输出/回执的凭据抑制 |
| NetStream | `test_netstream_transactions`：精确地址/端口、空目的、新对象、共享设置/AS、预算/聚合/monitor 拒绝、嵌套保护、来源隔离、精确删除及名字记录恢复 |

回执 JSON 中包含逐项及参数化子用例结果。上述表格描述软件合同覆盖，不证明固件接受、原生对象或数据面行为。

## 证据与执行边界

证据根：`C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL/work/software-verification-20261011/4589032fc5584d0b8cfedfa7c6cbee41`。

- `baseline-files.json`、`baseline/`、`head.txt`、`status.txt`、`diff.txt`：修改前的源码/测试快照、哈希和既有改动。
- `runs/c648afa0515e4c62a17756b70275c543/`：最终源码结果、日志、manifest。
- `candidate-runs/5a2a6356c48e42d09bd2c54a350d14e8/`：最终 wheel 结果、日志、manifest；实际导入为新 venv 的 site-packages。
- `dependencies.txt`、`candidate.json`、`build.log`、`pip-check.txt`：版本、构建和字节核对。
- 全部中间 `runs/` 回执保留，包括首轮新增失败、密钥遮蔽失败、损坏历史失败及测试夹具/Windows subprocess tripwire 适配失败。原 68 项失败日志另在旧软件测试目录，未覆盖。

父进程及 SDK 子进程强制 `MCP_HCL_ALLOW_LIVE_WRITE=0`。新增事务使用临时工程、脚本化回应、独立预期配置和可控时钟；未注入的 subprocess、原生管道构造和 Windows 采集 API 有测试阻断。执行器及 SDK 子进程另有 subprocess 审计，只允许启动软件 MCP server，两组审计均通过。已有诊断测试使用 Windows 私有合成 named pipe，涉及真实 Windows API，但没有访问 HCL/guest 控制台。

本次没有启动 HCL/guest、原生配置写入、流量测试、账号删除、提交、合并或 push；没有重采主账号资产/实验账号现场状态。旧现场证据仍停留在 2026-10-06。

原生全设备/线缆库存、IOS ingress-role/池掩码数据面、clock_rate/EIGRP delay、旧 PVST/protect/restrict、原生命名 exporter/monitor、完整审计规则、安全 Phone 原生关联仍为 NotImplemented 或缺口。生命周期隔离、真实独占 CLI、配置/startup/重启、认证明密文对应、BPDU/MAC 学习、collector 收包与有线/无线流量仍为 Unverified。

## 复现软件验证

```powershell
Set-Location 'C:\Users\w8p1p\.codex\worktrees\nat-transactions\MCP_HCL'
$mcpEvidence = 'C:\Users\w8p1p\.codex\worktrees\nat-transactions\MCP_HCL\work\software-verification-20261011\4589032fc5584d0b8cfedfa7c6cbee41'
$mcpReceipt = Get-Content "$mcpEvidence\runs\c648afa0515e4c62a17756b70275c543\result.json" -Raw | ConvertFrom-Json
$mcpModules = $mcpReceipt.modules
& "$mcpEvidence\venv\Scripts\python.exe" scripts\run_software_verification.py --receipt-root "$mcpEvidence\runs" @mcpModules
```

这条命令显式使用当前 src，并为每轮创建新目录。测试已完成，无新改动或未决问题时不需要重复执行。机器迁移时重建独立环境并使用保存的固定依赖版本。

机器可读结果、完整合同对应关系和未决项见 [software-verification-20261011.json](software-verification-20261011.json)。原生接手步骤见 [live-acceptance.md](live-acceptance.md)。
