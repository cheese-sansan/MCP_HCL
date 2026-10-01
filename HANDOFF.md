# MCP_HCL Agent 交接

> **本文是唯一的 Agent 交接文档。** 目标、边界、环境、接口契约、协议事实、代码地图、测试与回执、路线图、危险区、下一步全部在这里。
> 面向项目进度与评估的说明见 [README.md](README.md)。分支：`dsh`。更新：2026-10-01。

---

## 0. 五分钟上手

```powershell
# 基线必须是绿的：66 项通过（1 项因账号无 symlink 权限 skip）
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests

# 冒烟：以只读方式看能力面（不写任何东西）
$env:MCP_HCL_PROJECT_ROOTS = 'E:\MCP_HCL\work\feasibility\gate_20260930'
$env:MCP_HCL_OUTPUT_ROOT  = 'E:\MCP_HCL\work\staged'
$env:MCP_HCL_INSTALL_ROOT = 'D:\HCL'
E:\MCP_HCL\.venv\Scripts\python.exe -m mcp_hcl.server   # stdio，等协议输入
```

三条最容易踩的规则：

1. **文件层与控制层是两回事。** `hcl_stage_*` 只写工程文件，`status: staged` **不代表当前画布变了**。
2. **控制平面默认全关。** 任何改状态的动作都要 `MCP_HCL_ALLOW_LIVE_WRITE=1`，否则一律 `writes_disabled`。
3. **拓扑上下文绑定在 TCP 连接上。** 一次性连接发拓扑域动词会得到 `errorCode=228`。

---

## 1. 目标与验收定义

目标：在 HCL 5.10.3 中复现固定上游版本 [`Mats2208/MCP-Packet-Tracer@846db38`](https://github.com/Mats2208/MCP-Packet-Tracer/tree/846db381bc2c6ee0229d56e1d7ce8847eb6b213d)（61 工具 / 5 资源）的 HCL 功能等价能力，**必须实时控制并回读**。

"等价"必须分三级声明，否则无法判断完成度：

| 级别 | 含义 | 判据 |
| --- | --- | --- |
| **L1 接口等价** | 同名工具存在，参数能表达同一意图 | 客户端 `tools/list` 可见、schema 可表达 |
| **L2 效果等价** | 在 HCL 上产生与 PT 相同的可观察效果 | 工程文件 / 画布 / 设备状态的可观察变化 |
| **L3 证据等价** | 有与请求绑定的回读证据，失败可归因 | `operation_id` + 回读 + 回执 |

当前只有 4 项达到 L1+L3 的窄范围（`list_devices`/`get_device_details`/`list_projects`/`bridge_status`，`verified_scope` 分别限定在安装资料与后端协议回读）。每一项最终都要么达到 L1+L2+L3，要么给出"明确不支持/无原生等价"的结论与依据。

平台差异（不得照搬上游假设）：`.pkt` → HCL `.net`；IOS JavaScript → Comware；ACL object 需以相同 ACL 效果并通过 CLI 回读验证；NetFlow → NetStream 按固件支持验证；抓包与逐事件仿真分别验收，**捕获帧不能证明回退或逐 OSI 层决策日志存在**。

---

## 2. 边界与授权

**必须延续**

- 默认保护原工程；修改只在副本。不分发 HCL 程序、镜像或用户配置。上游 MIT 代码如复用需保留署名。
- 使用 `.net` 与 Comware，不沿用 `.pkt`、IOS JavaScript 或 HTTP/file 桥假设。
- 后台执行但未同步画布、文件 staging、旧响应、焦点丢失、失败 ping 或丢包**都不能报告实时成功**。保留失败与请求关联证据。
- **减少不必要测试**：已有成功回执沿用，只验证新风险、新客户端本次调用和剩余必需门槛。
- 耗时超过一分钟的启动/网络验收由使用者触发；重启由使用者操作。

**已获得的授权（2026-10-01）**

- 使用者作为设备所有者授权更激进地执行 P2（控制平面）与 P4（引导配置），并启用了 Windows 11 内置 `sudo`。
- 允许在 `dsh` 分支提交；**不允许**改动其他分支。
- **未**授权：commit 到其他分支、push、PR、发布、更换共享 VirtualBox、删除历史回执。

**仍然不要做**

- 不静默关闭 Windows 安全功能；不自动重启；不把 BCD 默认项改掉。
- 不用 LLM 识图或固定像素坐标作为产品级控制面。
- 不把"配置已生成"说成"配置已下发"，不把"命令返回"说成"网络连通"，不推断 PT 的逐事件仿真语义。

---

## 3. 环境与启动

| 项目 | 值 |
| --- | --- |
| 仓库 / 分支 | `E:\MCP_HCL` / `dsh` |
| Python | 项目 `.venv`，3.12.14（本机无可用 `py` 命令） |
| SDK / Pydantic | `mcp` 1.30.0 / `pydantic` 2.13.5；约束 `mcp>=1.28,<2`、`pydantic>=2.11,<3` |
| HCL | 5.10.3，`D:\HCL`，GUI 进程 `SimwareClient` |
| VirtualBox | 6.0.14，`C:\Program Files\Oracle\VirtualBox` |
| 后端 | `SimwareWrapper` TCP `127.0.0.1:16600`（**可脱离 GUI 独立运行**） |
| Windows | 11 build 26200，外壳是 **Windows PowerShell 5.1**（默认 ANSI = `gb2312`） |
| 本机 shell 陷阱 | `Get-Content -Raw \| ConvertFrom-Json` 读 UTF-8 无 BOM 的中文 JSON（如阶段工程 `project.json`）会解码损坏；必须显式 `-Encoding UTF8` |

### 推荐配置（只允许测试隔离副本）

```json
{
  "mcpServers": {
    "hcl": {
      "command": "E:\\MCP_HCL\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_hcl.server"],
      "env": {
        "MCP_HCL_PROJECT_ROOTS": "E:\\MCP_HCL\\work\\feasibility\\gate_20260930",
        "MCP_HCL_OUTPUT_ROOT": "E:\\MCP_HCL\\work\\staged",
        "MCP_HCL_INSTALL_ROOT": "D:\\HCL",
        "MCP_HCL_BACKEND_PORT": "16600"
      }
    }
  }
}
```

**要改状态才加** `"MCP_HCL_ALLOW_LIVE_WRITE": "1"`，且先确认 `working_directory` 指向隔离副本。

### 环境变量

| 变量 | 作用 |
| --- | --- |
| `MCP_HCL_ALLOW_LIVE_WRITE` | **总开关**，认 `1/true/yes/on`。关闭时所有改状态动作一律 `writes_disabled`。 |
| `MCP_HCL_PROJECT_ROOTS` | 分号分隔；工程路径与 `working_directory` 必须落在其中之一 |
| `MCP_HCL_OUTPUT_ROOT` | 阶段输出根，默认启动工作目录下 `work/staged` |
| `MCP_HCL_INSTALL_ROOT` | 默认 `D:\HCL` |
| `MCP_HCL_BACKEND_PORT` | 默认 16600 |

默认值：`PROJECT_ROOTS` 为当前用户 `HCL\Projects`。stdio Server 等待协议输入，终端无输出不代表卡死。更换代码/配置后要重启 MCP 子进程；工具数或版本不符时先查旧进程、旧安装或环境变量。

---

## 4. 当前接口面：15 工具 / 3 资源

### 4.1 只读与业务（原有 11 个，5 个保持旧结构兼容）

| 工具 | 输入 | 行为及局限 |
| --- | --- | --- |
| `hcl_capabilities` | 无 | 能力/注册清单；不是实时状态 |
| `hcl_list_projects` | 无 | 列根目录**下一层**有效工程，不递归 |
| `hcl_inspect_project` | `project_path` | **接受工程目录，不接受 `.net` 文件**；返回设备/坐标/链路；`status=ok` 不是运行态；**不返回注释与配置正文** |
| `hcl_stage_copy` | `project_path,stage_name` | 独立副本，重写工作目录与工程名；不打开画布 |
| `hcl_stage_add_device` | 上述 + `template_device,new_name,x,y`，可选三连线参数 | 克隆已有型号字段；三个可选连线参数必须一起给 |
| `hcl_stage_link` | `project_path,stage_name,a,a_port,b,b_port` | 副本写双端连接；只检查格式、名称、占用 |
| `hcl_parity_report` | 无 | 固定 61/5 映射与真实注册面；`completion=incomplete` |
| `hcl_bridge_status` | 无 | 后端版本/内存回读；不含工程、电源或 CLI |
| `hcl_list_devices` | 无 | **型号目录，不是当前拓扑设备列表**；来自本地 default CFG |
| `hcl_get_device_details` | `model` | 一个已安装型号的默认资料；不是运行设备查询 |
| `hcl_validate_plan` | `plan` 对象 | 版本化结构与部分端口/地址语义；`valid=true` 不证明部署或连通 |

资源：`hcl://capabilities`、`hcl://catalog/devices`、`hcl://catalog/ports`（3 个；`resources/templates` 为 0）。

### 4.2 控制平面（新增 4 个，默认全部关闭）

| 工具 | 契约 |
| --- | --- |
| `hcl_backend_capabilities` | **离线**列出 16 个已观察动词、证据等级与门控状态；`verified_scope="observed_verb_registry_only"` |
| `hcl_backend_topology` | `action` ∈ `open`/`close`/`status`。`open` 需要 `topology` 与配置根内的 `working_directory`；**保持一条持久连接**供后续拓扑域动词复用；同一时刻只允许一个会话（否则 `session_already_open`） |
| `hcl_device_power` | `device`,`on`。`on=False` → `unsupported`（**没有任何停止动词被观察到**）；需已开会话，否则 `no_open_session`；写开关先于会话检查 |
| `hcl_console_exec` | `command`，二选一给 `pipe` 或 `topology`+`device`，可选 `expect`。只接受 `\\.\pipe\<topo>-device<N>`；命令前到达的陈旧输出被丢弃并计入 `discarded_stale_bytes` |

控制平面的结果字段刻意分层：`verified_scope`（如 `backend_accepted_the_command_only`、`console_channel_text_readback_only`）+ `runtime_verified` / `guest_boot_verified` / `configuration_verified` / `connectivity_verified` / `full_live_gate_passed` **全部为 false**。

> 这 4 个**不是上游等价声明**：61 项映射中没有任何一行因它们的出现变为 implemented。

### 4.3 计划输入示例（`hcl_validate_plan`）

```json
{
  "schema_version": 1,
  "name": "两路由器实验",
  "devices": [
    {"id": "r1", "name": "路由器一", "model": "MSR36-20", "x": 0, "y": 0},
    {"id": "r2", "name": "路由器二", "model": "MSR36-20", "x": 200, "y": 0}
  ],
  "links": [{"a": {"device": "r1", "interface": "GigabitEthernet0/0"},
             "b": {"device": "r2", "interface": "GigabitEthernet0/0"}, "medium": "ethernet"}],
  "addresses": [
    {"device": "r1", "interface": "GigabitEthernet0/0", "cidr": "10.0.0.1/30"},
    {"device": "r2", "interface": "GigabitEthernet0/0", "cidr": "10.0.0.2/30"}
  ],
  "routes": [], "services": [],
  "annotations": [{"text": "隔离实验", "x": 0, "y": 100}]
}
```

计划用 **Comware 接口名**（`GigabitEthernet0/0`）；`.net` 用**场景端口键**（`GE_0/0`）。不能混用。

**已实现检查**：重复设备 ID/名称、未知型号、未知设备引用、未知物理接口、`NULL0` 拒绝、重复端口、自连接、serial/ethernet 介质不匹配、重复 IP、同接口同地址族重复、IPv4 网络/广播地址、路由地址族。
**明确未实现**：网段/网关可达性、下一跳可达性（两者都**不检查**，已用测试固定）、VLAN/VRF/路由邻接/无线语义、完整 secondary address（同接口同族第二条会被拒）。
`services` 只保存意图并返回 `feature_runtime_unverified`，不生成也不下发配置。

---

## 5. 61 项上游差距：按"需要什么才能做"分类

| 依赖类 | 数量 | 含义 | 已实现 |
| --- | --- | --- | --- |
| **D0 离线** | 14 | 不需要 HCL 进程，纯计算或本地文件 | 3 |
| **D1 后端控制平面** | 19 | 需要 SimwareWrapper + 让 HCL 载入工程，**不需要 guest 启动** | 1 |
| **D2 需要已启动 guest** | 24 | 需要控制台 CLI，因此需要 guest 真正启动 | 0 |
| **D3 无原生等价证据** | 3 | PT 专有逐事件仿真语义 | 0 |
| **D4 需视觉验收** | 1 | 截图，单模态 Agent 无法验收 | 0 |

- **D0（14）** 规划 5、目录 5（`list_devices`✅ `get_device_details`✅ `list_projects`✅ `list_modules` `list_templates`）、生成 4（`export` `generate_configs` `generate_script` `load_project`）。资源 `catalog/aliases`、`catalog/cables`、`catalog/templates` 也属此类。
- **D1（19）** 编辑 9、画布 2（`add_note` `clear_annotations`）、会话 5（`bridge_status`✅ `open_project` `save_project` `query_topology` `export_topology`）、备份工作区 2、检查 1（`device_power`）。
- **D2（24）** 策略 6、网络配置 5、遥测 2、验证 3、备份 1、检查 3、会话 2（`send_raw` `live_deploy`）、交付 2。
- **D3（3）** `read_packet_trace`、`simulation_mode`、`simulation_step`。
- **D4（1）** `screenshot`。

**关键结论**：设备启动阻塞只影响 D2 的 24 项，不是全部。**D0 有 11 项今天就能做，而且完全可离线回归。**

---

## 6. 控制平面协议事实（观察所得，非厂商文档）

证据来源：HCL 自带的运行日志与配置文件的**只读**检查——没有反编译、没有修改厂商文件、没有把厂商程序或镜像放进仓库。

### 6.1 传输与帧格式

```
请求 : <id> <service> <verb> [args...]\n        service ∈ {simwarewrapper, simware}
应答 : <id>-<code>[-<payload>]\r\n/end
```

**三条必须记住的规则（原始字节抓取所得）**

1. **回复没有参数时，`-payload` 整段省略**，不是 `-None`：`b'222222222-100\r\n/end'`。
2. 客户端断开后 Wrapper 会把"读到空请求"当成新请求，**补发一个无人认领的帧**（`errorCode=200`）。因此解析必须**按请求 ID 匹配**，不能"读到 `/end` 就当答案"。
3. **只接受已由 `/end` 终结的帧**。放松这条会让 TCP 分片悄悄截断数值（本仓库真实发生过一次）。

### 6.2 `errorCode`

| 码 | 观测到的含义 |
| --- | --- |
| `100` | 成功，无参数 |
| `101` | 成功，带参数 |
| `200` | 通用错误 / 空请求补发帧 |
| `204` `210` | 失败（历史日志） |
| `219` | `startVM` 失败（本次：拓扑存在但设备不存在） |
| `228` | **没有拓扑上下文** |

`_SUCCESS_CODES = {100, 101}`；其余按失败**返回给调用方**，不抛异常。

### 6.3 拓扑上下文绑定在 TCP 连接上（最重要）

同一次实验里同一个 `start 1 0` 得到两个结果，日志给出解释：

```
# 新连接直接 start
handle_one_request None, command is 'do_simware_start'      -> errorCode=228

# 同一连接先 create_topology
handle_one_request None, command is 'do_simware_create_topology'
SimwareTopo __init__, TopoName is mcphcl1, TopoPath is 'e:\...\v7_sw_vlan_basic', TopoUDPPort is 10000
SimwareWrapperRequestHandler v7_sw_vlan_basic send_reply(done=1, errorCode=100)
...
handle_one_request v7_sw_vlan_basic, command is 'do_simware_start'
SimwareTopo startVM                                          -> errorCode=219
```

处理器名由 `None` 变为拓扑路径目录名，说明连接获得了拓扑身份。**`create_topology` 参数语义经日志确认**：`<TopoName> <TopoPath> <项目名> <TopoUDPPort>`。

### 6.4 动词注册表（16 项）

| 动词 | service | kind | evidence | 可调用 | 默认启用 |
| --- | --- | --- | --- | --- | --- |
| `version` | simwarewrapper | read | verified | 是 | 是 |
| `system_memory` | simwarewrapper | read | verified | 是 | 是 |
| `create_topology` | simware | topology | observed | 是 | 否（写） |
| `start` | simware | power | observed | 是 | 否（写） |
| `start_recover` | simware | power | observed | 是 | 否（写） |
| `delete_udp` | simware | console | observed | 是 | 否（写） |
| `normal_close` | simware | lifecycle | observed | 是 | 否（写） |
| `set_hcl_tcp` | simware | lifecycle | observed | 是 | 否（写） |
| `set_hcl_normal_close` | simware | lifecycle | observed | 是 | 否（写） |
| `create_udp` | simware | console | inferred | **否** | 否 |
| `create` | simware | device | inferred | **否** | 否 |
| `delete` | simware | device | inferred | **否** | 否 |
| `set_memory` | simware | device | inferred | **否** | 否 |
| `set_version_path` | simware | device | inferred | **否** | 否 |
| `save` | simware | lifecycle | inferred | **否** | 否 |

**为什么 `create` 不可调用**：14 个位置参数中 6 个语义未知，而 `delete` 的参数形状也没采全——猜错会造出**删不掉**的虚拟机。宁可拒绝，也不要留下垃圾。

### 6.5 设备控制台

- 每个设备的控制台是一个 Windows 命名管道，名字确定性为 `\\.\pipe\<topology>-device<N>`（管道名也由 `create_udp` 的应答返回）。
- HCL 自己的控制台是 **PuTTY 串口模式**指向该管道（`D:\HCL\sessions\default_conf`：`Protocol=serial`、`PortNumber\115200`）。
- 因此 **CLI 通道是字节流，不需要窗口自动化或按键合成**。
- 本仓库客户端只接受该模式的管道名（无法指向任意宿主管道），用**非阻塞轮询**读写（不用读线程，避免 `close` 死锁；已实测 Windows 11 + Python 3.12 支持）。

### 6.6 路径与端口映射

- 每台设备一个 VirtualBox 虚拟机，由基础模板克隆（`GetVMByName, strName=Simware_Base` → `SimwareVM clone`）。
- 目录布局：`C:\Users\<用户>\HCL VMs\<拓扑名>\device<N>\<拓扑名>-device<N>.vbox`。
- `create` 请求携带该型号完整的**场景端口表**，元组第二项是端口类型 ID；`D:\HCL\deviceInfo.ini` 的 `[PHY_PORT_VALUE]` 给出同一套编号（`PHY_ETH_GE=3`、`PHY_ETH_XGE=4`、`PHY_ETH_FGE=5`）。
  → **"型号 → 场景端口"映射可以完全离线推导**，这正是文档长期列为缺失的一项；当前 `hcl://catalog/ports` 只返回端口族定义，**尚未做这个连接**。

---

## 7. 代码地图

| 文件 | 职责 | 关键点 |
| --- | --- | --- |
| `src/mcp_hcl/server.py` | stdio 工具/资源、环境配置、业务错误包装 | 15 个工具；控制平面会话状态 `session_lock`/`session_state`（同时只允许一个后端会话） |
| `src/mcp_hcl/backend.py` | 后端协议层 | `OBSERVED_VERBS` 动词注册表（唯一白名单，无透传）；`_frames()` 帧解析；`_Wire` 单连接收发；`_invoke()` 门控与整形；`BackendSession` 持久会话；`HclBackend._request` 是**未改语义**的只读窄路径 |
| `src/mcp_hcl/console.py` | 命名管道设备控制台 | `PIPE_PATTERN`/`describe()`/`endpoint()` 白名单；`open_console_pipe()` 非阻塞打开；`ConsoleSession` 轮询读写与 `drain()`；`HclConsole.run()` 组装证据 |
| `src/mcp_hcl/project.py` | `.net` 解析、路径保护、模板克隆、阶段提交 | 保留未知字段/中文名/Non-vBox 注释；临时目录组装后 rename |
| `src/mcp_hcl/topology.py` | Pydantic 计划及局部校验 | `extra='forbid'`、`allow_inf_nan=False` |
| `src/mcp_hcl/catalog.py` | 本地 CFG/INI 读取、来源哈希 | 不内嵌厂商文件 |
| `src/mcp_hcl/parity.py` + `data/upstream_parity.json` | 注册集合、61/5 清单、来源指纹 | `REGISTERED_TOOLS` 15 项 |
| `src/mcp_hcl/geometry.py` | 局部画布变换 | **尚未接入实时 MCP**；只覆盖 2 个观察型号 |
| `scripts/hcl_lab_boot.ps1` | 实验启动项 `Create`/`Remove`/`Arm`/`Disarm` | 非 MCP 接口；需提权 |
| `scripts/hcl_lab_environment.ps1` | 重启后只读会话判定 | 非 MCP 接口 |
| `scripts/hcl_open_gate.ps1` | 隔离开启/保存探针 | 非 MCP 接口 |
| `scripts/hcl_environment_snapshot.ps1` | 只读环境快照 | 非 MCP 接口 |
| `tests/` | 66 项 | 见 §8 |

---

## 8. 测试与回执

```powershell
# 全量（66 项，1 项因账号无 symlink 权限 skip）
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests

# 控制平面专项
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_backend_verbs tests.test_console -v

# 真实后端验证（自行启动并停止 Wrapper；不需要 GUI、不需要 guest）
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 E:\MCP_HCL\work\feasibility\dsh-20261001\p2_live_probe.py
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 E:\MCP_HCL\work\feasibility\dsh-20261001\capture_frames.py
```

| 测试文件 | 覆盖 |
| --- | --- |
| `test_backend.py` | 原有 4 项：真实 socket 往返、请求 ID 不符被拒、内存非法不被版本掩盖、非环回/变更命令被拒 |
| `test_backend_verbs.py` | 注册表与证据等级；写门控；不可调用动词；参数不能破坏行格式；逐条断言渲染命令行；错误码不抛异常；不可达记 `unverified`；**帧解析三条规则**；**per-connection 拓扑规则**（一次性连接 228 / 会话内 100） |
| `test_console.py` | 管道名白名单；写门控；危险命令拒绝；陈旧输出被丢弃；空读超时语义；**真实命名管道往返**（`CreateNamedPipeW` + `ctypes`，非 mock） |
| `test_mcp_contract.py` | 发现面、61/5 清单、计划校验矩阵、"已实现/未实现"边界、路径安全、命名语法、参数边界、控制平面工具必须门控且不宣称实时成功 |
| `test_project.py` / `test_topology.py` / `test_catalog.py` / `test_parity.py` / `test_geometry.py` / `test_live_gate_script.py` / `test_stdio.py` | 工程、计划、目录、清单、几何、脚本预检、stdio 发现 |

**回执索引**（`work/` 被 Git 忽略，换机器不存在）

| 断言 | 证据 |
| --- | --- |
| 控制平面真实后端验证、写开关、per-connection、未留下虚拟机 | `work/feasibility/dsh-20261001/p2-live-verification.json` |
| 每种动词的原始字节 | `capture_frames.py` 输出 |
| 命名管道非阻塞可用 | `probe_nonblocking.py`、`console-test-run2.txt` |
| 单模态纯 MCP 验收（分层结论） | `work/feasibility/single-modal-20261001/receipt-20261001.json` |
| 阶段副本 / 后端回读历史 | `work/feasibility/stdio-stage-copy-20261001.json`、`backend-status-20261001.json` |
| 子门槛历史（`full_live_gate_passed=false`） | `work/feasibility/open_gate_20261001/`、`step-runs/` |
| 环境/BCD/VBS/VM 只读快照 | `work/feasibility/environment_20261001/`、`.../device6-VBox.log` |
| 目录快照 | `work/feasibility/catalog-20261001.json` |
| P4 启动项 / 一次性引导 / 回退 | `work/feasibility/lab_boot_20261001/*/result.json`、`*/lab-environment.json` |

---

## 9. 路线图与验收

依赖顺序：**P0 → P1 → P2 → P3 → P4 → P5 → P6**，但 P1 与 P4 可并行（互不依赖）。

### P0 契约硬化
范围：严格参数校验（拒绝未知参数名，明确可选参数联动）；统一结果信封（`status/operation_id/request_id/target/verified_scope/evidence/errors[{code,message}]/warnings`）；结构错误也映射出 `code`；损坏工程一律业务 `rejected`；引入可选 `idempotency_key`。
验收：`test_mcp_contract.py` 全绿 + 新增严格参数用例；5 个旧接口保持字段兼容。

### P1 离线层（11 工具 + 3 资源，最大收益，零外部依赖）
范围：`list_modules`、`list_templates`、三个目录资源；`plan_topology`、`estimate_plan`、`explain_plan`、`fix_plan`、补全 `validate_plan` 的服务参数校验；`load_project`、`export`、`generate_configs`、`generate_script`；**顺带把 `deviceInfo.ini` 与型号接口列表连接成真正的"型号 → 场景端口"映射**。
验收：implemented 从 4 升到约 18；新增用例全部离线可回归；生成物标注 `runtime_verified=false`，**不声称任何命令被设备接受**。

### P2 控制平面 —— **第一层已完成**
已完成：动词注册表（16 项，逐项标 evidence/writes）、写总开关、帧解析（三条规则）、持久连接会话、命名管道控制台客户端、4 个 MCP 工具、测试。
已用真实后端验证：版本/内存读回；`create_topology` 被接受（`100`）；同一会话内 `start` 进入 `SimwareTopo startVM`；`normal_close` 干净回收且**未留下任何虚拟机**；写开关关闭时三个工具全部 `writes_disabled`；开关打开也不假装成功（无设备 → 无管道 → 如实 `unverified`）。
仍缺：`create`/`delete`/`create_udp` 字段语义、命名管道并发语义、GUI 是否重读后端拓扑。

### P3 画布与工程闭环（relay）
`阶段写盘 → HCL 打开副本 → HCL 自行 create/create_udp 重建画布 → HCL 保存 → 回读 .net + 查询后端`。
只有"打开/保存"走窗口自动化，其余全部确定性。编辑类 9 项先用 relay 实现；注释 2 项本就是 `.net` 的 `[Non-vBox-DATA]` 段（实测 4 个 `[[NOTE n]]`），属纯文件编辑。
验收：每次编辑后 `query_topology` 与 `.net` 回读一致；源工程哈希不变；操作与请求绑定。

### P4 引导配置 —— **条目已建立、一次性引导已武装，等使用者重启**
见 §10。

### P5 D2 的 24 项 CLI 家族
有了 P2 的管道客户端和 P4 的可用 guest，这层是批量工程：`apply_*`（VLAN/STP/端口安全/加固/接口调优/ACL/NAT/NetStream）、`read_vlans`/`read_qos`/`inspect_ports`、`audit_security`、`backup_config`、`verify_connectivity`、`diff`、`health_check`、`send_raw`、`deploy`/`full_build`/`live_deploy`。
共同验收：每条配置命令都要 CLI 回读；`deploy` 必须能报告哪几条成功、哪几条被固件拒绝；`verify_connectivity` 不能用"命令返回 0"代替丢包统计。

### P6 收口
3 项仿真语义维持 unverified 并写清"HCL 无原生逐事件回退/逐 OSI 层决策日志"；`screenshot` 的验收交给有视觉的一方或改为结构化导出并声明不是像素等价；每项 implemented 都带 `verified_scope` 与回执路径，`completion` 才能从 `incomplete` 走向可度量。

---

## 10. P4 现状与使用者操作

### 事实

| 时间 | 事件 | 证据 |
| --- | --- | --- |
| 15:48 | 第一次 `Create` 成功，条目 `{1031110f-…}` | `2704c0bf…/result.json`（`verified`） |
| 16:16 | 只读判定 `not_booted_into_lab_entry`，随后回退删除 | `2455f377…/lab-environment.json`、`a5eeece9…/result.json` |
| — | **系统自 2026-09-30 01:24:52 起未重启** | `systeminfo` 与 `LastBootUpTime` 两来源一致 |
| 16:2x | 条目**重建**为 `{10311110-…}`，一次性引导**已武装** | `55c95115…/result.json`、`ae5381b1…/result.json` |

第一次尝试没进实验项，归因是启动菜单 `default` 是 `{current}`、`timeout` 30 秒、实验项被追加在**最后**——"人工在菜单里抢时间"会静默失败。这已由 `Arm` 消除。

### 当前引导状态

| 项 | 值 |
| --- | --- |
| 启动项 | `{10311110-89bd-11f0-ad29-c0bfbeee1ce7}` — `MCP_HCL Lab (Hypervisor and VSM off)` |
| 回读 | `hypervisorlaunchtype Off`、`vsmlaunchtype Off` |
| 一次性引导 | `{bootmgr}` 的 `bootsequence {10311110-…}`（启动后自动清除，`default` 不动） |
| `default` / `displayorder` | 仍 `{current}`；实验项也在 `displayorder` 里，作为人工选菜单的退路 |
| BCD 备份 | `2704c0bf…/bcd-before.bak`，SHA256 `2D849DC815CF3A5551EDF4B3B09DFA1539FEAE0384250B528CA93DE68305FB4A` |

### 使用者动作

**用「重启」（Restart），不要用「关机」（Shutdown）** —— 快速启动可能恢复上次内核会话、跳过引导流程，且 `LastBootUpTime` 不更新（这正是第一次难以判断的原因）。重启走完整流程，`bootsequence` 生效，**不需要在菜单里做任何选择**。

该会话的 Hypervisor/VBS 防护与依赖功能不可用——一次性的显式选择，日常启动项未受影响。

重启后：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_environment.ps1 `
  -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
```

`verdict=lab_entry_active_and_no_hypervisor` 时才继续跑剩余电源门槛；仍是 `not_booted_into_lab_entry` 则退回"重启时在 30 秒菜单里选最后一项"。

### 提权与回退

本机 `sudo` 处于**强制新建窗口模式**（`sudo config` 如此报告）：`--inline` 会被拒绝，提权进程 stdout 不回调用终端。**凡提权动作都要用"写文件回执"取结果**，不要依赖管道输出。

```powershell
# 武装一次性引导
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Arm `
  -EntryId '{GUID}' -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001

# 清掉未生效的一次性引导（重启前）
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Disarm `
  -EntryId '{GUID}' -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001

# 删除实验项（必须先回到普通 Windows 项）
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Remove `
  -EntryId '{GUID}' -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
```

`Arm`/`Disarm` 的实现细节：不是每个引导管理器都接受 `bootsequence`——本机 `{fwbootmgr}` 能枚举但拒绝设置（`找不到元素`），脚本因此在 `{bootmgr}`/`{fwbootmgr}` 间依次尝试"设置 + 回读"，只接受真正回读成功者，两个都失败就明确报错并退回人工选菜单，**不假装成功**；两处都断言 `default` 未变。

> **备份是机器本地的**：`bcd-before.bak` 在 `work/` 下，`work/` 被 Git 忽略，清理它会丢。它只用于灾难恢复，日常回退用 `Remove` 即可。

---

## 11. 未验证 / 危险区

**未验证**

- `start` 在**同时存在真实设备**时能否真正拉起 guest。本机受 `VERR_NEM_VM_CREATE_FAILED` 阻塞；目前只证明"命令进入了 `SimwareTopo startVM`"。
- 控制台**实际输出**：管道只在设备控制台创建后才存在，当前 `FileNotFoundError` 是正确结果而非缺陷。
- **命名管道并发语义**：HCL 的 PuTTY 已连接时能否第二客户端接入、是否互斥、是否原始终字节流——**全未测**。设为 P5 可行性的判定项：结论为"不可共享"时 CLI 方案必须回到评审，改用 HCL 自己的控制台或 `SimwareMultiCC`。
- 符号链接防护：本机账号无 `SeCreateSymbolicLinkPrivilege`（WinError 1314），相关测试 skip，属**未验证**而非通过。
- 引导项设置正确 + 一次性引导已武装 ≠ guest 一定能起来；因果确认要等真正启动一台设备。

**危险区**

1. **不要在一次性连接上发拓扑域动词**（得到 `228`，且容易被误读成"设备不存在"）。
2. **不要放宽 `_frames` 的终结符要求**（会让 TCP 分片截断数值）。
3. **不要假设回复一定带 payload 段。**
4. **不要开 `create`**，除非先把字段补齐并且能删干净。
5. **后端直接改拓扑不会刷新 GUI 画布**，所以拓扑变更要走 relay。
6. 真实 Wrapper **会写虚拟机目录**；开写开关前确认 `topology` 与 `working_directory` 是隔离副本，并保留前后快照。
7. 单模态 Agent 不得声称审核过 PNG 内容；图像验收交给有视觉的一方。

---

## 12. 已核实的事实与对旧文档的更正

以下是旧交接文档中被本轮实测**更正或补充**的条目（旧文档已合并进本文）：

- `protocolVersion = 2025-11-25`；`resources/templates/list` 返回 **0**；`prompts/list` 为空但 capabilities 声明了 prompts 能力。
- **`isError` 是双向的**：`isError=false` 不等于业务成功，`isError=true` **也不等于** HCL 业务失败（缺必填参数、类型错误、未知工具都会是 `isError=true`）。真正的业务失败是 `isError=false` + `status=rejected`。
- `errors[]` 形状不一致：语义错误是 `{code,message}`，**结构错误是 pydantic 原始 `{type,loc,msg,url}`，没有 `code` 键**。
- 损坏工程（`device_id = abc`、`x = not-a-number`）会以**工具错误逃逸**而非业务 `rejected`；缺 `[vbox]`、两个 `[vbox]`、缺 `device_id`、重复字段、非对称链路、非 UTF-8 都已正确返回 `rejected`。
- **未知参数被静默忽略**：可选参数拼错会返回 `staged` 但没做那件事（例如 `connect_to` 写成 `connect_too` → 只加设备、不连线）。
- `operation_id` 每次调用重新生成，**不是可跨接口关联的稳定键**。
- `hcl://catalog/devices` 与 `hcl_list_devices` 的负载除 `operation_id` 外逐字段一致。
- `hcl_stage_copy` 保真度**高于**旧描述：副本 `.net` 与源**只差 `workingdir` 一行**，未知字段、中文设备名、注释块、`[Non-vBox-DATA]` 全部保留。注释就在 `[Non-vBox-DATA]` 的 `[[NOTE n]]` 中（该工程实测 4 条），只是**没有工具暴露它们**——所以 `add_note`/`clear_annotations` 属纯文件编辑。
- 实测 `D:\HCL` 与本用户工程的 `.net` 均为**无 BOM + CRLF**；读取端接受 BOM，写回端不写 BOM。
- 相对路径可用但按**服务端进程 cwd** 解析，结果依赖启动目录，客户端不应依赖。
- 原受保护工程 `.net` SHA-256 仍为 `CCC821A5FBA6F30AE0F20CBB5FB4029D39A9D5812068B6B40047A1E85A785570`，与历史记录一致。
- 状态口径：`ok` 只表示旧式保存工程检查完成；`staged` 只表示独立文件生成；`verified` 只在 `verified_scope` 限定层内成立；`input_sent` 必须配合后续回读才算效果。

---

## 13. 下一步（含验收）

1. **P0 契约硬化** —— 地基，成本最低，测试已就绪。
2. **P1 目录 2 项 + 3 个资源** —— 一天内可把 implemented 从 4 提到 9。
3. **P1 规划 4 项 + 型号端口映射** —— 纯计算层；端口映射可直接用 `deviceInfo.ini` 与 `devicecfgs` 离线推导。
4. **命名管道并发测量**（决定 P5 可行性）：在 HCL 的 PuTTY 已连接同一管道时尝试第二客户端；给"可并发/需互斥/不可共享"的明确结论与原始回执。
5. **补齐 `create`/`delete`/`create_udp`**：从 HCL 打开工程时的日志抓完整请求行与返回码。验收：在隔离拓扑上创建再删除一台设备，`vm_root` 前后一致。
6. **P4**：使用者重启后跑 `hcl_lab_environment.ps1`，然后启动一台隔离设备并读控制台。

### 改动纪律（请延续）

- 每个新动词必须标注 `evidence`（`verified`/`observed`/`inferred`）与是否 `writes`。
- 写动词默认 `invocable=False`，除非字段语义有据可依。
- 每个"成功"都要有 `verified_scope`，并且**不得跨层推断**：命令被接受 ≠ guest 启动 ≠ 配置下发 ≠ 网络连通。
- 任何对外部世界的成功声明都要附回执路径；回执进 `work/`（被 Git 忽略）。
- 只提交到 `dsh` 分支。
