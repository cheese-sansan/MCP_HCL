# MCP_HCL 当前工作交接

**先读这三个（按顺序）：**

1. [docs/roadmap.md](docs/roadmap.md) —— 目标定义、差距根因、61 项按依赖重新分类、分阶段实施顺序。**当前的行动依据。**
2. [docs/control-plane.md](docs/control-plane.md) —— 控制平面的**实现级**交接：代码地图、工具契约、已验证事实与逐条回执、危险区、下一步与验收标准。**接手代码前必读。**
3. [docs/hcl-backend-protocol.md](docs/hcl-backend-protocol.md) —— HCL 自带后端协议（SimwareWrapper）的观察记录：帧格式、动词、返回码、控制台管道。

决策记录：[ADR-0001 实时控制通道](docs/adr/0001-live-control-transport.md)（**Accepted**，第一层已实施并验证）。

[docs/handoff-single-modal.md](docs/handoff-single-modal.md) 已**归档**：它包含启动配置、接口限制、纯 MCP 验收步骤、故障证据与权限边界，仍然有效，但其中的"后续推进顺序"已被路线图取代，文末附有核实后的更正与补充。

更新：2026-10-01。本文件仅记录已确认事实；完整上游功能移植尚未完成。

## 目标与边界

- 固定上游 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d`，61 工具、5 资源。
- 用户要求 HCL 功能等价，必须实时控制、回读证明；保护源工程。
- 用户允许直接调用同权限外部 PowerShell。用户要求减少不必要测试，已有成功回执沿用，仅补新增风险和未完成门槛。
- 用户选择在当前电脑修复兼容性后继续。修改启动安全配置的独立启动项确认已提出，尚未收到该项答复，尚未执行 BCD 修改；不要将泛化修复选择解释为允许静默关闭所有 Windows 安全功能。
- 超过一分钟的启动/网络验收及重启由用户触发。未授权提交或推送。

## 当前实现

- 分支 `dsh`（自 `codex/hcl-live-parity` 的 `1005ac3f` 创建），版本 0.1.1。
- 原 5 个 MCP 接口保持兼容。共 **15 工具、3 资源**：11 个原有 + 4 个控制平面工具（`hcl_backend_capabilities`、`hcl_backend_topology`、`hcl_device_power`、`hcl_console_exec`），后者**默认全部关闭**，需 `MCP_HCL_ALLOW_LIVE_WRITE=1`。
- 控制平面已实现并**用真实后端验证**（动词注册表、写总开关、持久连接会话、命名管道控制台）。未在启动的 guest 上验证过。
- 本机测试基线：**66 项通过**（1 项因账号无 symlink 权限 skip）。
- `.net` 安全副本、只读后端协议回读、固定上游对照表、局部画布几何、打开/保存 PowerShell 探针。
- 本机型号/端口目录：8 个默认配置型号、11 个端口族，来源及 SHA-256 可读；不是当前固件能力证明。
- `TopologyPlan` v1 包含设备、链接、地址、静态路由、服务意图、注释。`hcl_validate_plan` 已实现结构、默认接口、端口占用及地址冲突检查；完整服务参数校验、生成与部署尚待完成。
- 未完成：一键构建、完整 Comware 工作流、实时通用控制适配层、CLI、连通性、审计、抓包等；逐项见 `docs/upstream-parity.md`。

## 实时门槛与环境阻碍

- 隔离工程：`E:\MCP_HCL\work\feasibility\gate_20260930\v7_sw_vlan_basic\v7_sw_vlan_basic.net`。
- 实际画布新增测试路由器并连线，保存 6 设备/5 链路；随后实际删除新链路，保存 6 设备/4 链路/4 注释。设备 `MSR36-20_6` 仍保留且关机，设备删除门槛未完成。
- HCL 5.10.3：`D:\HCL`；VirtualBox 6.0.14。
- 启动 VM6 失败，日志 `VERR_NEM_VM_CREATE_FAILED` / `VidStartVirtualProcessor` 错误 87，所有 VM 关机。未取得真实 CLI 输出。
- Win11 26200、HypervisorPresent=True、VBS 运行；当前 BCD hypervisorlaunchtype Auto。只读快照和失败日志：`work/feasibility/environment_20261001/92ba4f26c1db4cd58ac21ea012192366/`。
- VM6 UART2 为 `\\.\pipe\topo1-device6` 服务端管道，配置盘指向副本。仅为配置证据，不能声称 CLI 可用。
- HCL PID/句柄及画布滚动条必须重新读取。曾遇 LockApp，指针保护拒绝输入；窗口锁定时停止输入。
- 原工程 `.net` SHA-256：`CCC821A5FBA6F30AE0F20CBB5FB4029D39A9D5812068B6B40047A1E85A785570`，此前文件集合回执见 `work/feasibility/stdio-stage-copy-20261001.json`。

## 待确认的修复

**状态更新（2026-10-01）**：`scripts/hcl_lab_boot.ps1` 的 `Create` 与新增的 `Arm` 均已成功执行。实验启动项 `{10311110-89bd-11f0-ad29-c0bfbeee1ce7}`（`MCP_HCL Lab (Hypervisor and VSM off)`）已按 `hypervisorlaunchtype Off` / `vsmlaunchtype Off` 建立并回读；**一次性引导已武装**（`{bootmgr}` 的 `bootsequence`），下次启动直接进实验项、设置随之自动清除，`default` 未改动。BCD 已先备份，脚本未重启。

第一次尝试**没有真正进入实验项**：会话内 `bcdedit {current}` 仍是 `Windows 11` / `Auto`、`HyperVisorPresent=true`，系统自 2026-09-30 起未重启；已按计划回退删除旧条目。归因是启动菜单默认项 + 30 秒超时 + 实验项排在最后，人工选择会静默失败。`Arm`/`Disarm` 就是为了消除这个失效点。

剩余唯一动作：**使用者用「重启」进入实验项**（不要用「关机」，快速启动会跳过引导流程），然后跑只读的 `scripts/hcl_lab_environment.ps1` 判定。回退命令与完整回执见 [控制平面实现与交接](docs/control-plane.md) §10。

本机 `sudo` 处于**强制新建窗口模式**，`--inline` 会被拒绝；提权动作一律用"写文件回执"取结果，不要依赖管道输出。

详细命令、回执与恢复说明见 [docs/live-gate.md](docs/live-gate.md) 与 [docs/control-plane.md](docs/control-plane.md) §10。

## 验证策略与运行

此前 13 项离线测试已通过。此轮仅补 4 项新几何及 1 项修改脚本预检，全部通过；新增目录/计划逻辑与受影响契约的 9 项也通过。没有重复启动或全量画布验收。

```powershell
& 'E:\MCP_HCL\.venv\Scripts\python.exe' -m mcp_hcl.server
```

Python 的 `py` 命令不可用。构建运行时：`C:\Users\w8p1p\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`。可用 `pip wheel --no-deps --no-build-isolation . --wheel-dir work/wheels` 离线构建，避免重复公网依赖下载。
