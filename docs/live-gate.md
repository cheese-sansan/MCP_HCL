# HCL 实时控制验收门槛

完整功能移植依赖实时门槛通过。工程文件生成、后台调用成功、窗口点击完成均不能单独证明门槛通过。

## 当前证据

- HCL 5.10.3，安装路径 `D:\HCL`；原工程的 `.net` SHA-256 为 `CCC821A5FBA6F30AE0F20CBB5FB4029D39A9D5812068B6B40047A1E85A785570`。
- 2026-09-30 普通权限 PowerShell 向 HCL 窗口发送输入消息返回 Windows 错误 5。相同权限的进程能看到 Qt 控件完整树，并通过 Browse 按钮的 `InvokePattern` 打开文件选择框。
- 该次 `SetWindowText`/`BM_CLICK` 尝试未关闭文件选择框，未证明工程打开。
- 2026-10-01 原生 Computer Use 重新绑定当前 HCL 窗口后，首页点击未产生可观察的界面变化；实时门槛仍未通过。
- 2026-10-01 对本机 `127.0.0.1:16600` 完成只读后端探测：版本回读 `1.0.0&6.0.14`，内存回读 `14708` MB；两次响应均与各自请求 ID 匹配。仅验证版本及内存协议回读，回执 `live_canvas_verified` 与 `full_live_gate_passed` 均为 `false`。
- 2026-10-01 已自动打开隔离副本，核对 HCL 标题中的项目名及完整副本路径，并调用保存、回读 `.net`。该子步骤通过；完整实时门槛仍未通过。
- 在隔离画布实际新增 `MSR36-20_6` 并创建到核心交换机的 GigabitEthernet 连线。保存回读为 6 台设备、5 条链路；新增端口对为 `MSR36-20_6/GE_0/0` 和 `核心交换机_1/GE_0/2`。重复选择源接口曾触发 HCL 的“无法连接同一接口”拒绝，相关步骤及截图保留。
- 删除链路探测前发现画布平移：固定像素位置可能命中注释，未执行删除。已验证可通过当前滚动条值、缩放和 `.net` 场景坐标计算设备中心；目前只验证 MSR36-20 和 S5820V2-54QS-GE 的图标几何。
- 桌面曾进入锁屏，目标位置的进程为 `LockApp`；指针保护检查在点击前拒绝操作。用户允许继续后重新确认目标归属 HCL，才恢复桌面操作。
- 在正确的链路上下文菜单中确认“开启抓包”后删除新链路，保存回读为 6 台设备、4 条链路、4 项注释。测试设备仍保留在隔离副本，设备删除门槛尚未完成。
- 调用测试设备 `MSR36-20_6` 的“启动”后，VirtualBox 6.0.14 报 `VERR_NEM_VM_CREATE_FAILED`，日志记录 `VidStartVirtualProcessor` 错误 87。虚拟机状态回到 `poweroff`，没有运行中的虚拟机；不得报告设备启动成功。
- 当前系统为 Windows 11 build 26200，`HypervisorPresent=True`，VBS 状态为运行，当前 BCD 的 `hypervisorlaunchtype=Auto`。已保存只读快照及失败日志：`work/feasibility/environment_20261001/92ba4f26c1db4cd58ac21ea012192366/`。
- VM6 的配置盘指向隔离副本；UART2 配置为服务端管道 `\\.\pipe\topo1-device6`。这只是控制台传输配置证据；未取得已启动设备的 CLI 输出。

上述证据覆盖副本打开/保存、设备新增及链路增删；设备删除未完成，电源验收失败，CLI 和网络连通仍未验证。旧的 PID、窗口句柄及画布像素坐标不得复用。

## 当前电脑的兼容修复方案

[H3C 5.10.3 官方安装说明](https://www.h3c.com/cn/d_202404/2116237_30005_0.htm)建议 Windows 10、附带的 VirtualBox 6.0.14，并要求关闭 Hyper-V 相关功能和内存完整性。目前的失败与 Hypervisor/VBS 状态符合这一兼容阻碍，但重启后的真实启动验收才能确认修复效果。

`scripts/hcl_lab_boot.ps1` 为当前 Windows 创建独立的 `MCP_HCL Lab (Hypervisor and VSM off)` 启动项。脚本先导出 BCD 备份，只在副本上设置 `hypervisorlaunchtype=Off`、`vsmlaunchtype=Off`，添加到启动菜单并回读；不会自动重启、修改日常启动项或更换 VirtualBox。选择实验项时该会话的 Hypervisor/VSM 防护和依赖功能将不可用。

**2026-10-01 更新：创建与一次性引导均已成功执行。** 使用者启用 Windows 11 内置 `sudo` 并授权后，以提权方式执行：

```powershell
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Create `
  -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
# 然后武装一次性引导（下次启动直接进实验项，设置自动清除，default 不动）
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Arm `
  -EntryId '{10311110-89bd-11f0-ad29-c0bfbeee1ce7}' `
  -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
```

结果：启动项 `{10311110-89bd-11f0-ad29-c0bfbeee1ce7}`，回读 `hypervisorlaunchtype Off` / `vsmlaunchtype Off`；BCD 备份 SHA256 `2D849DC815CF3A5551EDF4B3B09DFA1539FEAE0384250B528CA93DE68305FB4A`；`default` 与 `{current}` 均未变；`bootsequence` 已武装并回读；未重启。

**第一次尝试没有进入实验项**：会话内 `bcdedit {current}` 仍是 `Windows 11` / `Auto`、`HyperVisorPresent=true`，系统自 2026-09-30 起未重启。只读判定脚本如实报 `not_booted_into_lab_entry`，旧条目随后被回退删除。归因是启动菜单默认项 + 30 秒超时 + 实验项排在最后——这正是新增 `Arm` 的原因。

**剩余动作由使用者完成：用「重启」（不是「关机」，快速启动会跳过引导流程）进入实验项**，随后运行只读的 `scripts/hcl_lab_environment.ps1` 判定会话状态。注意本机 `sudo` 处于强制新建窗口模式，提权进程的输出不会回到调用终端，因此一律以文件回执为准。详见 [控制平面实现与交接](control-plane.md) §10。

回退（先 `-Action Disarm` 清掉未生效的一次性引导，再在普通 Windows 项下 `-Action Remove`）：

```powershell
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Remove `
  -EntryId '{10311110-89bd-11f0-ad29-c0bfbeee1ce7}' `
  -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
```

创建回执会包含新 GUID、备份路径、命令退出码和回读。一次性引导生效后只执行一次剩余电源门槛；不要重跑已经通过的拓扑步骤。恢复普通启动后，可先用 `-Action Disarm` 清掉未生效的一次性引导，再用 `-Action Remove -EntryId '{回执中的GUID}'` 删除实验项——删除保护会拒绝当前或默认的实验启动项。

## 隔离工程打开与保存探针

`scripts/hcl_open_gate.ps1` 只接受仓库 `work/` 下的真实 `.net` 文件和回执目录，拒绝链接路径，并在打开前检查工作目录和设备配置路径；只在 HCL 首页开始。它通过控件标识打开文件选择框，核对文件名输入回读和画布中的独立项目名后，再调用保存按钮并读取工程文件。回执始终保留 `full_live_gate_passed: false`，因为设备、链路、电源和 CLI 尚未验证。

在与 HCL 相同 Windows 权限级别的 PowerShell 中执行。先确认仅有一个 HCL 实例：

```powershell
$hclInstances = @(Get-Process -Name SimwareClient -ErrorAction Stop)
if ($hclInstances.Count -ne 1) { throw '请只保留一个 HCL 实例，并停留在首页' }
& 'E:\MCP_HCL\scripts\hcl_open_gate.ps1' `
  -HclPid $hclInstances[0].Id `
  -ProjectFile 'E:\MCP_HCL\work\feasibility\gate_20260930\v7_sw_vlan_basic\v7_sw_vlan_basic.net' `
  -OutputDirectory 'E:\MCP_HCL\work\feasibility\open_gate_20261001'
```

回执根目录的 `result.json` 是最新结果；每次执行的 JSON 和截图保存在独立 `runs/` 子目录中，历史失败结果保留。失败不自动重试，以防重复打开或在焦点未知时输入。

追加 `-ValidateOnly` 可只验证副本路径、工作目录和 UTF-8 元数据，不操作 HCL；其 `verified_scope` 为 `isolated_project_preconditions_only`，不能计为实时控制验收通过。

## 后续通过条件

1. 在独立副本上增删设备及链路，保存后 `.net`、画布和后台状态一致。
2. 启停设备，画布和虚拟机状态一致。
3. 执行只读 Comware CLI，取得当前设备真实输出；ping 统计必须解析丢包。
4. 原工程所有文件哈希保持不变，操作结果与对应请求绑定。

超过一分钟的设备启动或网络测试由使用者触发；回执缺失时保留未验证状态。
