# 单设备原生测试及账号清理（2026-10-11）

本轮由用户授权 Codex 在此处完成必要测试并清理账号。单台 MSR36-20 的真实隔离生命周期通过；候选 CLI 独占检查阻塞，未发送命令；配置和网络测试未执行。整体仍 Incomplete，`full_live_gate_passed=false`。

证据根：`C:/Users/Public/Documents/MCP_HCL_Native_Test_20261011/c2f6bfc9fcb347d8a5b2f1d2f2fd0556`。候选 wheel SHA256：`3d3663ca1c65ffc9c93b5281a460469de3a0d1f39115307704e9775f33465f9a`。本轮未重跑软件回归，未修改软件代码。

## 已执行与实际边界

- 使用普通 SimwareClient.exe，实际 lab SID `S-1-5-21-246709277-55761766-931132026-1006`。环境与 Client/Wrapper/MultiCC/VBoxSVC/guest 所有者由实验进程采集，未覆盖用户环境根。
- 工程 `C:/Users/MCPHCLLab/Documents/HCL_Trials/Isolation_c2f6bfc9/v7_sw_vlan_basic/v7_sw_vlan_basic.net`，仅一台 LabIsolationRouter。打开后原生创建 VM `38a6fa2e-681b-4e77-acdc-d2944b272b8b`，正常启动一次、停止一次、保存并退出。
- lab VM 注册、差分盘、配置盘均定位在实验账号目录；UART `\\.\pipe\topo1-device6` 与该 VM 绑定。`created/running/stopped/exited/snapshot.json` 保存描述、注册、日志及进程证据。created 是工程加载后创建，不是模拟结果。
- 原账号 52 个运行时文件、32 个工程文件与注册文件在运行中、退出后、账号删除后完全一致。共享 boot.vdi/msr36_b75.vmdk 内容哈希和大小不变，修改时间变化；其他 vendor 文件仅比较大小、修改时间、首 64K 摘要，不能声称所有镜像全量哈希已验证。没有原资产恢复动作。
- 候选 wheel 内 `mcp_hcl.console.HclConsole` 的一次真实调用被 `external_console_present` 拒绝，`command_outcome=not_sent`。正常关闭本次 HCL 控制台容器后，后台 SimwareMultiCC 仍存在。未终止它或绕过保护；未重复请求。实际 display version、完整 CLI 字节/提示符归因、配置、startup 与流量仍未验证。
- 现场控制台可见固件启动输出和自动配置等待，但不是候选 CLI 的成功证据。
- HCL 正常保存/退出自行清理 lab 的 runtime VM 与注册，并将配置盘归档到工程的 `ConfigDisk_backup.zip`；不是账号删除脚本删除文件。不可声称临时 runtime 磁盘退出后仍存在。原始运行中描述/日志已留存。

## 账号清理

本轮到达 CLI 保护阻塞边界后结束，未扩大测试。按用户“测试完成后删除账户”指示，正常收尾并使用原创建回执、审阅脚本匹配 SID/唯一 description，先 Disable 后 Remove。两步均有 verified 回执，`cleanup-state.json` 为 `removed_verified`，名称/SID 现场查询均不存在。

`C:/Users/MCPHCLLab` 的 profile 记录和目录仍保留，Loaded=false；工程、ConfigDisk_backup.zip 和本轮证据仍保留，见 `preservation-after-removal.json`。仍观察到实验 VBoxSVC 后台进程，未强制终止；HCL/Wrapper/MultiCC/PuTTY/guest 均已退出。账号删除不证明产品验收完成，也不授权删除遗留目录。

凭据仅人工输入、内存使用，未写入 argv/文件/环境。凭据请求不可见、脚本 BOM 解析失败、清理模块/启动器失败均保留为准备阶段负面记录，没有改写成通过。

## 后续

先解决候选独占判定与 HCL 后台 MultiCC 的兼容问题、明确执行身份，再确定必要的 CLI 专项。不要重复本轮成功的启动/生命周期来证明同一事实。未来需要新的实验账号时须准备新的身份/隔离方案，不能假设 MCPHCLLab 仍存在。其余未实现能力和正式有线/无线门槛仍按统一测试计划保留。
