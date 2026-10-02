# MCP_HCL

一个与 Agent 客户端无关的 H3C Cloud Lab (HCL) MCP Server，目标是在 HCL 5.10.3 中复现固定上游版本 [MCP-Packet-Tracer@846db38](https://github.com/Mats2208/MCP-Packet-Tracer/tree/846db381bc2c6ee0229d56e1d7ce8847eb6b213d)（61 工具 / 5 资源）的 HCL 功能等价能力：**实时控制并回读**。

> **接手开发请读 [HANDOFF.md](HANDOFF.md)** —— 目标定义、接口契约、后端协议事实、代码地图、测试与回执、路线图、危险区都在那里。本文只描述**当前进度**。

---

## 进度摘要（2026-10-01）

| 项 | 值 |
| --- | --- |
| 版本 / 分支 | `0.1.1` / `dsh` |
| 注册面 | **15 工具、3 资源**（11 原有 + 4 控制平面，后者默认关闭） |
| 上游映射 | 61 工具 **4 implemented / 54 planned / 3 unverified**；5 资源 2/3/0；`completion=incomplete` |
| 本机测试 | **66 项通过**（1 项因账号无 symlink 权限 skip） |
| 实时闭环 | 后端控制平面已打通并**对真实后端验证**；guest 启动仍受阻塞 |

### 分层状态

| 层 | 状态 | 说明 |
| --- | --- | --- |
| 连接与发现 | ✅ 通过 | 15 工具、3 资源、`protocolVersion 2025-11-25` |
| 已注册只读接口 | ✅ 通过 | 目录 / 工程 / 型号 / 端口族 / 能力 / 映射均按声明工作 |
| 计划校验 | ✅ 通过 | 结构、端口、地址、路由地址族；服务的协议语义仍缺 |
| 阶段生成与回读 | ✅ 通过 | `stage_copy` 6/4 → `add_device` 7/4 → `stage_link` 7/5，源工程逐字节不变 |
| **控制平面（新增）** | ✅ 第一层完成 | 动词注册表 + 写门控 + 持久会话 + 命名管道控制台；真实后端验证 |
| 设备启动 / CLI / 连通性 | ⛔ 未完成 | 受 Hypervisor/VBS 阻塞；引导项已就绪，等使用者重启 |
| 全部上游等价 | ⛔ Incomplete | 54 项 planned |

### 61 项按"需要什么才能做"分类

| 依赖类 | 数量 | 已实现 | 说明 |
| --- | --- | --- | --- |
| **D0 离线** | 14 | 3 | 规划 5、目录 5、生成 4 —— **11 项今天就能做，不受任何阻塞影响** |
| **D1 后端控制平面** | 19 | 1 | 需要 Wrapper + 让 HCL 载入工程，**不需要 guest 启动** |
| **D2 需要已启动 guest** | 24 | 0 | CLI 家族，受 Hypervisor 阻塞 |
| **D3 无原生等价证据** | 3 | 0 | PT 专有逐事件仿真语义 |
| **D4 需视觉验收** | 1 | 0 | 截图 |

**关键判断**：设备启动阻塞只影响 D2 的 24 项，不是全部。项目此前把"实时门槛"当成全局前置，这是本轮纠正的主要偏差。

---

## 当前能力（15 工具 / 3 资源）

### 只读与阶段生成（11）

`hcl_capabilities`、`hcl_list_projects`、`hcl_inspect_project`、`hcl_stage_copy`、`hcl_stage_add_device`、`hcl_stage_link`、`hcl_parity_report`、`hcl_bridge_status`、`hcl_list_devices`、`hcl_get_device_details`、`hcl_validate_plan`。

资源：`hcl://capabilities`、`hcl://catalog/devices`、`hcl://catalog/ports`。

`status: staged` 表示**新工程文件已生成，当前画布未改变**；调用方需自行在 HCL 中打开结果。

### 控制平面（4，默认全部关闭）

| 工具 | 作用 |
| --- | --- |
| `hcl_backend_capabilities` | 离线列出 16 个已观察后端动词、证据等级与门控状态 |
| `hcl_backend_topology` | 打开/查询/关闭后端拓扑会话（持久连接；同一时刻仅一个） |
| `hcl_device_power` | 上电（**只观察到上电，没有停止动词**，故 `on=False` 报不支持） |
| `hcl_console_exec` | 向设备控制台命名管道发送一行并回读 |

这 4 个需要 `MCP_HCL_ALLOW_LIVE_WRITE=1` 才会执行；关闭时一律返回 `writes_disabled`。它们**不是上游等价声明**。

---

## 本轮完成的关键突破

1. **实时控制不再依赖窗口自动化。** HCL 自带后端协议（`SimwareWrapper`，TCP 16600），并且**可以脱离 GUI 独立启动**——这使协议能够安全、可重复地验证，不需要 HCL 界面、不需要 guest。
2. **CLI 通道定位明确。** 每个设备的控制台是命名管道 `\\.\pipe\<topology>-device<N>`，HCL 自己的 PuTTY 以串口模式连接它。因此 CLI 是字节流，不需要按键合成。
3. **写门控与证据分层落地。** 所有改状态动作默认关闭；每个结果都带 `verified_scope`，且 `guest_boot_verified` / `configuration_verified` / `connectivity_verified` 一律为 false，不跨层推断。
4. **引导项已就绪。** 实验启动项已按 `hypervisorlaunchtype Off` / `vsmlaunchtype Off` 建立，并武装了**一次性引导**（下次启动直接进实验项，设置自动清除，默认项不动）。

已用真实后端验证：版本/内存读回（`1.0.0&6.0.14` / `14708`）、`create_topology` 被接受、同一会话内 `start` 进入 `SimwareTopo startVM`、干净关闭且**未留下任何虚拟机**、写开关关闭时全部拒绝。

---

## 已知阻塞与下一步

**阻塞**：guest 无法启动（`VERR_NEM_VM_CREATE_FAILED`）。根因已由 VirtualBox 自身日志定位——**WHPX 分区创建成功（`NEM: Created partition`），失败点是 `VidStartVirtualProcessor` 返回 `dwErr=87` 并触发断言 `cbInput == sizeof(HV_VP_INDEX)`**，即 VirtualBox 6.0.14 假定的 WHPX IOCTL 参数尺寸与当前 Windows 构建的 API 不一致。**不是缺 WHPX 功能，也不是安全设置没关。**

由此：

- 唯一已知的有效做法是启动时关闭 Hypervisor/VSM，但那需要额外启动菜单项——**设备所有者已明确否决**（要求保持正常 Windows 开机体验、不接受实验改动系统启动配置）。相关启动项与一次性引导已清除并独立复核。
- 在"不改启动配置 + 不换 VirtualBox"的前提下没有非侵入式解法。
- 因此 **24 项 CLI 家族暂时无法推进**；但 **D0 + D1 共 33 项完全不受影响**，其中 29 项仍待实现。详见 [HANDOFF.md](HANDOFF.md) §10。

**下一步优先级**（不含被阻塞项）

1. P0 契约硬化剩余部分：未知参数名拒绝（需中间件，函数层看不到多余参数）、`request_id` 回显、`idempotency_key`。结构错误统一与损坏工程拒绝已完成。
2. P1 离线层：`list_modules`、`list_templates` + 3 个目录资源；`plan_topology`/`estimate`/`explain`/`fix`；`export`/`generate_configs`/`generate_script`/`load_project`；并离线推导"型号 → 场景端口"映射。
3. P3 注释编辑（纯文件层）与 relay 闭环验证。
4. 命名管道并发测量：不依赖 guest 启动，但仍决定 CLI 家族未来的可行性。

---

## 安装与运行

需要 Windows、Python 3.11+ 及合法安装的 HCL。命令在 PowerShell 中从仓库执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

本机无 `py` 命令时用已有 Python 的绝对路径代替第一行。

```powershell
$env:MCP_HCL_PROJECT_ROOTS = 'C:\Users\YOUR_NAME\HCL\Projects'
$env:MCP_HCL_OUTPUT_ROOT  = 'E:\YOUR_WORKSPACE\MCP_HCL\work\staged'
.\.venv\Scripts\python.exe -m mcp_hcl.server
```

`MCP_HCL_PROJECT_ROOTS` 可用分号分隔多个绝对目录。将同一命令与环境变量配置到任意支持 stdio MCP 的客户端即可，不需要特定 Agent 的推理代码。

**要执行会改状态的动作**（设备上电、控制台输入、后端拓扑），额外设置 `MCP_HCL_ALLOW_LIVE_WRITE=1`，并确认操作对象是隔离副本。默认值、全部环境变量与客户端配置示例见 [HANDOFF.md](HANDOFF.md) §3。

## 验证

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests
```

预期 `Ran 66 tests` + `OK (skipped=1)`。骨架测试使用合成 HCL 安装与临时工程，不读写 `D:\HCL`、真实用户工程或 `work/staged`；控制台测试会创建**真实**的 Windows 命名管道。

```powershell
# 真实后端验证（自行启动并停止 Wrapper；不需要 GUI、不需要 guest）
.\.venv\Scripts\python.exe -X utf8 work\feasibility\dsh-20261001\p2_live_probe.py
```

---

## 边界

- 默认保护原工程，修改只发生在副本；仓库不包含 HCL 程序、镜像、用户工程或设备配置。
- 未验证的运行态功能不会被声称成功：`full_live_gate_passed` 始终为 `false`，直到真正启动设备并取得 CLI 回读。
- 后端协议是**观察所得**的未公开接口，仅对 HCL 5.10.3 + VirtualBox 6.0.14 声明有效。
- `work/` 被 Git 忽略，包含回执、阶段工程与虚拟磁盘副本，**不要提交**。

LICENSE：MIT。上游接口名称与映射来自固定提交，未移植上游运行代码。
