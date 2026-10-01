# MCP_HCL

一个与 Agent 客户端无关的 H3C Cloud Lab (HCL) MCP Server。当前版本针对 Windows HCL 5.10.3 已实测的**工程文件载入路径**：读取现有 `.net` 工程，在独立副本中阶段性加入设备或链路，然后由使用者在 HCL 中打开该副本。代码采用 MIT 许可证；仓库不包含 HCL 程序、镜像、用户工程或设备配置。

## 当前能力与边界

| MCP 工具 | 行为 |
| --- | --- |
| `hcl_capabilities` | 报告已实现能力和激活边界 |
| `hcl_list_projects` | 列出配置的项目根目录下一层工程 |
| `hcl_inspect_project` | 只读解析设备、坐标和链路 |
| `hcl_stage_add_device` | 从工程已有的同型号设备复制模型字段，生成一个**独立工程副本**；可同时加入一条链路 |
| `hcl_stage_link` | 在独立工程副本中为两个空闲端口加入双端链路 |
| `hcl_stage_copy` | 生成保持设备、链路、配置和注释的独立工程副本，用于实时控制验收 |
| `hcl_parity_report` | 返回固定上游版本的 61 项工具、5 项资源对照清单及真实实现状态 |
| `hcl_bridge_status` | 只读查询本机 HCL 后端版本与内存，绑定请求 ID 回读；不代表画布或 CLI 控制已验证 |
| `hcl_list_devices` | 从本机 HCL 默认配置生成型号和默认接口目录，附来源及 SHA-256 |
| `hcl_get_device_details` | 读取一个已安装型号的默认固件字符串和接口；运行态能力仍待探测 |
| `hcl_validate_plan` | 校验版本化计划、设备引用、端口占用、地址冲突和路由地址族；服务固件支持保留警告 |

### 控制平面（新增，默认全部关闭）

下列 4 个工具驱动 HCL 自带的后端协议与设备控制台命名管道。它们**不是上游等价声明**，且**任何会改变状态的动作默认被拒绝**，必须先以 `MCP_HCL_ALLOW_LIVE_WRITE=1` 启动服务端。实现与验证细节见 [控制平面实现与交接](docs/control-plane.md)。

| MCP 工具 | 行为 | 默认 |
| --- | --- | --- |
| `hcl_backend_capabilities` | 离线列出已观察到的后端动词、证据等级与门控状态 | 只读，可用 |
| `hcl_backend_topology` | 打开/查询/关闭一个后端拓扑会话（拓扑上下文绑定在 TCP 连接上） | 写，关闭 |
| `hcl_device_power` | 通过已观察动词上电（**没有观察到任何停止动词**，`on=False` 报不支持） | 写，关闭 |
| `hcl_console_exec` | 向设备控制台命名管道发送一行并回读；只接受 `\\.\pipe\<topo>-device<N>` | 写，关闭 |

另提供只读资源 `hcl://capabilities`、`hcl://catalog/devices`、`hcl://catalog/ports`。目录读取本地安装资料，不包含或分发厂商配置、程序和镜像。`MCP_HCL_INSTALL_ROOT` 默认 `D:\HCL`，可设为实际安装目录。

完整 HCL 等价功能移植尚未完成。当前注册 **15 个工具、3 个资源**（其中 4 个是控制平面工具，默认关闭）；计划中的目标名称不代表已实现。

**先读 [路线图](docs/roadmap.md)**：它把 61 项上游工具按"需要什么才能做"重新分成四类——**14 项完全不依赖实时能力**（其中 11 项仍待实现）、19 项只需后端控制平面、24 项才需要已启动的 guest、3 项无原生等价证据。设备启动确实被本机 VirtualBox/Hypervisor 兼容问题阻塞，但该阻塞只影响第三类。控制平面的选择见 [ADR-0001](docs/adr/0001-live-control-transport.md)，实现与逐条回执见 [控制平面](docs/control-plane.md)，HCL 自带后端协议的观察记录见 [后端协议](docs/hcl-backend-protocol.md)。

其他文档：[实时验收说明](docs/live-gate.md)、[上游功能对照表](docs/upstream-parity.md)、[Agent 使用指南](docs/agent-guide.md)、[单模态交接（已归档）](docs/handoff-single-modal.md)。

`status: staged` 表示新工程文件已生成，**不表示当前 HCL 画布已改变**。调用方必须打开结果中的 `project_file`，再观察 HCL 画布与运行日志。仍然**没有**"打开/保存当前画布"、连通性测试或直接编辑当前画布的工具；设备上电与控制台输入虽然已有工具，但默认全部关闭，且尚未在真正启动的 guest 上验证过。

工具只接受配置的项目根目录内的工程。新设备使用工程中已有设备作为型号模板；端口名称会检查格式和占用情况，但**尚未核对该 HCL 型号是否实际提供指定端口**。HCL 载入工程是最后的兼容性校验。阶段名只允许 1–20 位 ASCII 字母、数字和下划线，生成目录不得已存在。

## 安装与启动

需要 Windows、Python 3.11+ 及合法安装的 HCL。以下命令在 PowerShell 中从本仓库执行，把依赖安装到本项目的 `.venv`：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

本机开发环境没有 `py` 命令时，可用已有 Python 的绝对路径代替第一行。项目依赖固定在 MCP Python SDK 1.x；2.x 的高层 Server 导入路径不同。

配置项目根目录与阶段输出目录，然后启动 stdio Server：

```powershell
$env:MCP_HCL_PROJECT_ROOTS = 'C:\Users\YOUR_NAME\HCL\Projects'
$env:MCP_HCL_OUTPUT_ROOT = 'E:\YOUR_WORKSPACE\MCP_HCL\work\staged'
.\.venv\Scripts\python.exe -m mcp_hcl.server
```

`MCP_HCL_PROJECT_ROOTS` 可用分号隔开多个绝对目录。若未设置，默认读取当前用户的 `HCL\Projects`；`MCP_HCL_OUTPUT_ROOT` 默认是启动时工作目录下的 `work\staged`。将同一命令和环境变量配置到任意支持 stdio MCP 的客户端即可，不需要特定 Agent 的推理代码。

`hcl_bridge_status` 默认连接本机 `127.0.0.1:16600`，可以通过 `MCP_HCL_BACKEND_PORT` 修改端口。它只发送 HCL 5.10.3 已观察到的版本与内存查询；`status: verified` 的范围由 `verified_scope` 限定为后端协议回读。

## 使用顺序

1. 用 `hcl_list_projects` 或 `hcl_inspect_project` 确认源工程及其设备名、已有端口。
2. 用 `hcl_stage_add_device` 或 `hcl_stage_link` 生成阶段工程。要在同一批次继续修改，把上次返回的 `project_directory` 作为下次的 `project_path`，并使用新的 `stage_name`。
3. 在 HCL 中打开最终返回的 `.net` 文件，确认画布设备与链路；设备未启动时不能把拓扑加载成功解释为网络连通。

阶段工程放在 `work/` 下并被 Git 忽略。源工程文件从不原地修改。生成前检查设备 ID、名称和端口占用；输出目录使用临时目录组装后再命名为最终阶段目录。不要把 `work/` 内的 HCL 工程、VDI/VMDK 或配置文件加入开源仓库。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

实测基线（2026-09-29，HCL 5.10.3）：通过真实 MCP stdio 客户端调用 `hcl_stage_add_device`，从 6 台设备、5 条链路的工程生成包含第 7 台路由器 `MCP_R8` 和第 6 条链路的阶段工程。HCL 重新打开该工程后，日志记录 `MCP_R8` 的 `NETFile::create_node`、新链路的 `NETFile::add_connection`；仿真后端双向 `create_udp` 都返回成功，VirtualBox 的第 7 台虚拟机配置盘指向阶段工程，状态为关机。原工程文件未改变。

后端内部接口单独创建设备并不会自动更新当前画布，因此本版本不把后端调用包装成“实时 GUI 创建”。上述验收证明拓扑加载，不证明设备启动、Comware 配置或网络连通性。
