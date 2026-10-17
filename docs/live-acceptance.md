# 测试与原生验收指南

## 软件检查

既有规范化快照的软件回归为 330 项：329 通过、1 符号链接权限跳过；候选受影响专项 177 项：176 通过、1 跳过。完整 SDK 声明 55 工具/6 资源保持，Ruff 和依赖检查通过。结果绑定其 manifest，不能推广到以后变化的代码。

```powershell
.\.venv\Scripts\python.exe scripts\check_all.py
```

统一入口强制真实写开关为 0，核对实际导入路径并保存独立回执。新代码或未决问题只做受影响测试，复用范围匹配的有效证据，不无理由重跑完整旧回归。类型/Schema、默认门控、模拟来源、身份、幂等、保存/回执失败和原 UUID 恢复均须保持合同。

源码或候选变化时先固定 SHA 与依赖，不能混用旧 editable 工作区。当前 API 对照增量本机完整 346 项（345 通过、1 跳过），新安装候选 SDK/协议/API 专项 40 项（39 通过、1 跳过）。前一提交 2f7ec0f 的云端 338 项结果及旧候选 143 项结果保留，仅证明当时源码/包范围；新 CI 结果按实际提交核对。

新候选与当前证据定位见 [HANDOFF](../HANDOFF.md)，支持和拒绝范围见 [合同](contract-v2.md)。

## 原生接手前提

已记录一次单设备隔离生命周期成功；旧候选独占 CLI 被后台 MultiCC 保护拒绝，命令未发送，配置/网络未执行。MCPHCLLab 已删除，profile、工程和证据保留。最新现场状态必须只读复核；不能假设旧账号仍存在或自动重建。

接手先核对真实 SID/CIM profile、profile/AppData/Temp、Client/Wrapper/VBoxSVC/guest 所有者、监听者、运行时根/注册、原账号资产以及工程可读性。不得覆盖用户环境根、搬入原账号 VM/注册、修改镜像 UUID，或把单独 .net/workingdir 当成运行时隔离。

SimwareClient 是已有普通入口，身份可能因 UAC 变化；出现提权/身份变化时停止，不输入管理员凭据，不修改 manifest、BCD、安全功能或二进制，不自动重启。不得终止他人的 PuTTY/MultiCC 或绕过独占保护。

## 必要执行顺序

1. 固定实际候选与源码，完成相关软件检查和身份/资产只读复核。
2. 复用有效成功生命周期；只有新变化或未决隔离要求才安排新的单设备范围，不重复启动证明同一事实。
3. 确认实际管道为单实例字节流、保留原生错误并验证执行身份后，仅做必要独占 CLI 回显、完整字节和提示符归因。拒绝、占用、截断、超时保留，不重放或模拟通过。
4. CLI 与隔离前提满足后，明确相关功能支持范围；先备份并验证恢复入口，再做必要配置及网络验证。失败恢复同一 UUID，分别报告 running、startup、流量与重启。

原生完整库存、未接受 IOS/Comware 映射、命名 exporter/monitor、完整审计规则及安全 Phone 等软件缺口不能靠重复测试闭合，按 NotImplemented/Unverified 记录。

## 完整交付门槛

有线：3 MSR36-20、3 S5820V2-54QS-GE，每 LAN 2 PC DHCP；三路由器线性 /30，LAN /24，OSPF 1/area 0；4 条方向 FULL 邻居、远端 LAN 路由、6 唯一租约/网关，LAN 两两双向各 5 包零丢包。

无线：1 AC、1 AP、1 交换机、2 Phone，管理 VLAN 1/业务 VLAN 10；真实 WPA2-PSK、2 唯一租约和双向各 5 包零丢包。安全 Phone 原生关联/持久化/恢复未完成时停止于该门槛，不以开放 Wi-Fi、有线或 AP CLI 替代。这些完整门槛不自动扩大当前必要测试任务。

## 回执与收尾

每组回执记录源码/候选 SHA、环境/执行方、operation_id、具名用例及 Passed/Failed/Unverified/NotImplemented/Skipped、证据路径、修改与恢复、未决项和原资产前后状态。声明/Schema、协议、原生配置、隔离和流量分层；没有证据保持 false/unknown，full_live_gate_passed=false 直至完整门槛实际满足。

新操作用新目录，保留失败。配置、PSK、截图、原始控制台和恢复备份私有保存，不入 Git/wheel。工程缺失、权限拒绝或观察器期限不能补写为通过。

旧账号的停用/删除已完成，不再次对同名账号执行旧命令。未来账号或宿主动作需对应授权、可审阅身份与回退步骤；账号清理不授权删除 profile、工程、VM、磁盘、日志或证据。

## 当前复现推进

上游固定到 3c7c7a46（62 工具/5 资源）。目标覆盖全部实时控制、原生库存、配置语义、有线闭环、无线、观察、安全审计、模拟/工作区、独立 DHCP Server、API 对应与交付证据，详见 HANDOFF 和 hcl_parity_report 的 reproduction_targets。

当前 CLI 增量已在私有 Windows 管道测试：后台进程存在不直接代表目标占用；连接必须证明只有一个字节流实例。未知或多个实例拒绝，不能以取消独占检查解决兼容。真实 VirtualBox 管道若声明多个/无限实例，需要继续建立可验证的实际消费者归属方案，不降低标准。

最近只读接手复核没有观察到 MCPHCLLab 账号及 Client/Wrapper/MultiCC/guest 进程。真实测试需先准备已审阅的非提权身份、隔离工程和资产基线；不自动重建账号或启动 guest。原生最小验项为实际 GetNamedPipeInfo/服务器 PID/SID/UUID/配置盘归因、占用/未知拒绝、display version 完整回显与提示符。结果绑定新候选 SHA，旧失败保留。

用户已授权临时普通账号进行最基础测试；2026-10-12 最小预检在环境检查被拒绝，账号已回退删除，profile 与失败记录保留，未启动 HCL/guest。当时未记录具体失败字段，不能事后补写根因或通过。真实 CLI 专项保持 Unverified。API 对应软件测试检查全部 62/5 的声明覆盖、源/快照 SHA、实际 SDK Schema、缺入口、参数包装/默认差异及错误/结果未知标志；不执行映射目标，不导入上游注册器，不升级原生验收。

后续先用本次创建回执、已审阅的实际 profile 和观察器 SHA 准备只读启动计划，不能照抄历史 SID。以下命令在原账号 Windows PowerShell 5.1 中执行，PlanOnly 不询问密码或启动子进程：

```powershell
$observerSha = (Get-FileHash scripts\hcl_lab_environment_identity.ps1).Hash.ToLowerInvariant()
scripts\hcl_lab_observation_launch.ps1 -CreationRecord '本次创建回执.json' -ExpectedProfile '本次实际profile路径' -ObserverSha256 $observerSha -OutputRoot '已审阅的私有回执目录' -PlanOnly
```

输出包含 14 项检查及明确字段；环境匹配返回 0，拒绝或未知返回 2。通过只表示当前身份及路径字符串匹配，不证明路径无链接、VM 隔离、HCL/guest 或 CLI 可用，也不授权启动。不要用修改 USERPROFILE/AppData/Temp 或降低检查来制造通过。脚本仅选择已知路径/token 字段，不导出完整环境；回执留在本地私有证据目录。

确认计划后，去掉 PlanOnly 才会在原账号进程中读取 SecureString 密码并请求目标账号子进程。目标账号必须已有与创建 SID 匹配的 CIM profile；未初始化时在凭据输入/启动之前拒绝。工作目录固定为该 profile，不能使用 SystemRoot 或回执目录替代；本机跨账号实测发现后者会进入 HOMEDRIVE/HOMEPATH。

新账号的执行策略可能拒绝 `-File`。启动器按 SHA 读取同一缓冲区后使用 Command 模式运行固定观察器，不更改执行策略，不使用 ExecutionPolicy Bypass。读取固定系统模块也不改写 PSModulePath。等待超时返回 3，保留该 PID，先观察同一子进程；不能因为观察超时重新创建账号或重放启动。日志区分 profile_load_requested 与 profile_loaded_for_child，后者不凭启动请求写为 true。

2026-10-18 两次必要只读尝试及回退分别位于 `C:/Users/Public/Documents/MCP_HCL_ReadOnly_20261018/86b79cf7245a49e4b5da269e97cc2422/`、`C:/Users/Public/Documents/MCP_HCL_ReadOnly_20261018/770a2178352a48bc911bba5066c8d347/`。前次在 File 模式被执行策略拒绝；修正后取得 14 字段，其中 13 项匹配、HOME 组合项指向回执工作目录。TEMP/TMP 的 8.3 路径经规范化指向正确 profile，不能按字符串前缀误判。两个新账号均按各自 SID/标记停用删除，profile/证据保留；未启动 HCL/guest，未发送 CLI。该新观察不补写 2026-10-12 的未知字段。
