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

`status: staged` 表示新工程文件已生成，**不表示当前 HCL 画布已改变**。调用方必须打开结果中的 `project_file`，再观察 HCL 画布与运行日志。当前不提供自动打开工程、设备启动、Console CLI、连通性测试或直接控制当前画布的工具。

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
