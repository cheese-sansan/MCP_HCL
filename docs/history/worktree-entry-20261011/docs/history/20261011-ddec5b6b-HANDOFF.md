# MCP_HCL Agent 交接

> **本文是唯一的 Agent 交接文档。** 目标、边界、环境、接口契约、协议事实、代码地图、测试与回执、路线图、危险区、下一步全部在这里。
> 面向项目进度与评估的说明见 [README.md](README.md)。分支：`dsh-2`。更新：2026-10-05。当前机器与试验状态以 §17 为准；前文旧版本/数量属于历史应用基线。

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

- **不要改动系统启动配置。** 设备所有者 2026-10-02 明确否决了"额外启动菜单项 / 下次优先进入实验模式"的做法，要求保持正常 Windows 开机体验。`scripts/hcl_lab_boot.ps1` 的 `Create`/`Arm` 不得再使用，除非重新获得明确授权。
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
| 引导配置已还原（无实验项、无 bootsequence） | `work/feasibility/lab_boot_20261001/bcd-after-cleanup.json` |
| 提权读 BCD（2026-10-02 发现条目消失） | `work/feasibility/lab_boot_20261001/bcd-report-20261002.json` |
| Hyper-V/VBS/可选功能现状 | `work/feasibility/lab_boot_20261001/hypervisor-report-20261002.json` |
| 方案 B 评估：HCL 二进制里的版本字面量扫描与上下文 | `work/feasibility/dsh-20261001/vbox-version-scan.txt`、`vbox-version-context.txt` |
| 方案 B 评估脚本（只读） | `work/feasibility/dsh-20261001/scan_vbox_version.py`、`dump_strings.py` |

---

## 9. 路线图与验收

依赖顺序：**P0 → P1 → P2 → P3 → P4 → P5 → P6**，但 P1 与 P4 可并行（互不依赖）。

### P0 契约硬化 —— **部分完成**
范围：严格参数校验（拒绝未知参数名，明确可选参数联动）；统一结果信封（`status/operation_id/request_id/target/verified_scope/evidence/errors[{code,message}]/warnings`）；结构错误也映射出 `code`；损坏工程一律业务 `rejected`；引入可选 `idempotency_key`。
验收：`test_mcp_contract.py` 全绿 + 新增严格参数用例；5 个旧接口保持字段兼容。

> **已完成（2026-10-02，`dsh-2`）**
> - **结构错误统一形状**：`hcl_validate_plan` 的结构错误现在也是 `{code: "invalid_plan_structure", message, loc, detail:{type}}`，客户端可统一按 `errors[].code` 分支。
> - **损坏工程不再以工具错误逃逸**：`project.py` 新增 `_field_integer` / `_field_number`，`device_id = abc`、`x = not-a-number` 等一律返回业务 `rejected`；非有限坐标同样被拒。
> - 两项都由 `test_mcp_contract.py` 固定（原先的 characterization 测试已改成契约断言）。
>
> **仍缺**：未知参数名被 FastMCP 在进入工具函数前丢弃，**函数层根本看不到多余参数**——要拒绝它必须做中间件或原始请求校验，**不要**用加 `**kwargs` 之类的办法糊过去。`request_id` 回显与 `idempotency_key` 也尚未实现。

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

### P4 guest 启动 —— **启动配置方案（A）被所有者否决；B 已只读评估；D2 保持阻塞**
根因是 VirtualBox 6.0.14 的 WHPX 实现与本机 Windows 构建不兼容（日志证据见 §10.2），**不是配置没调对、也不是缺 WHPX 功能**。在"不改启动配置 + 不换 VirtualBox"的前提下没有非侵入式解法。

- **方案 A（关闭 Hypervisor/VSM）**：已实现并验证过，但**被所有者否决**（改变系统启动配置），条目与 `bootsequence` 已清除。
- **方案 B（升级 VirtualBox 到 6.1+）**：**只读评估已完成**——HCL 不校验版本、路径与绑定方式兼容（见 §10.3"已排除的障碍"），但 `vboxapi` 与 VM 配置格式升级**只读无法证明**；结论是"带真实回退风险的机器级试验"，仍需授权。
- 因此 P5 的 24 项 CLI 家族**暂时无法推进**；把精力放在 D0/D1（33 项，见 §10.4）。

### P5 D2 的 24 项 CLI 家族
有了 P2 的管道客户端和 P4 的可用 guest，这层是批量工程：`apply_*`（VLAN/STP/端口安全/加固/接口调优/ACL/NAT/NetStream）、`read_vlans`/`read_qos`/`inspect_ports`、`audit_security`、`backup_config`、`verify_connectivity`、`diff`、`health_check`、`send_raw`、`deploy`/`full_build`/`live_deploy`。
共同验收：每条配置命令都要 CLI 回读；`deploy` 必须能报告哪几条成功、哪几条被固件拒绝；`verify_connectivity` 不能用"命令返回 0"代替丢包统计。

### P6 收口
3 项仿真语义维持 unverified 并写清"HCL 无原生逐事件回退/逐 OSI 层决策日志"；`screenshot` 的验收交给有视觉的一方或改为结构化导出并声明不是像素等价；每项 implemented 都带 `verified_scope` 与回执路径，`completion` 才能从 `incomplete` 走向可度量。

---

## 10. P4 现状：方案 A 被所有者否决、方案 B 已只读评估但未授权 —— guest 启动当前不可用

### 10.1 决定（2026-10-02，设备所有者）

**不要改动系统启动配置。** 设备所有者明确表示：HCL 实验额外添加启动菜单项、并设置"下次优先进入关闭 Hypervisor/VSM 的实验模式"，**不符合其保持正常 Windows 开机体验、避免实验改变系统启动配置的意愿**，因此该方案被否决。

10-01 与 10-02 建立的实验启动项与 `bootsequence` 已由所有者清理；我随后（在得知该意愿之前）重建的那一套，也已按要求清除并独立复核：

| 复核项 | 结果 |
| --- | --- |
| `{10311111-…}` 实验项 | **不存在**（`osloader` 只剩 Windows 11 与 Windows Recovery Environment） |
| `{bootmgr}` 的 `bootsequence` | **不存在** |
| Disarm / Remove 回执 | 均 `status=verified`（`c7ad1fec…`、`95909812…`） |
| 独立复核 | `bcd-after-cleanup.json` |

**结论：不要再用 `scripts/hcl_lab_boot.ps1` 的 `Create`/`Arm` 触碰启动配置**，除非所有者重新明确授权。脚本保留在仓库里仅作为工具与历史记录。

### 10.2 根因：VirtualBox 6.0.14 的 WHPX 实现与本机 Windows 不兼容（不是缺功能，也不是安全设置）

保存的失败日志 `work/feasibility/environment_20261001/92ba4f26c1db4cd58ac21ea012192366/device6-VBox.log`（SHA256 `F1360EC2…9F30`）给出了此前从未被读透的关键行：

```
NEM: VidGetHvPartitionId            -> fun:0x2210c3 in:0x0 out:0x8
AssertLogRel ... nemR3WinIoctlDetector_StartVirtualProcessor(...): cbInput == sizeof(HV_VP_INDEX)
RTErrInfoSet(VERR_NEM_RING3_ONLY): Problem figuring out VidStartVirtualProcessor: fRet=0 dwErr=87
NEM: Disabling UseRing0Runloop.
NEM: Created partition 000000000174cc20.
NEM: Adjusting APIC configuration from X2APIC to APIC max mode.  X2APIC is not supported by the WinHvPlatform API!
NEM: Not available: Problem figuring out VidStartVirtualProcessor: fRet=0 dwErr=87
NEM: NEMR3Init: Active.
VMSetError: ...NEMR3Native-win.cpp(1408)... rc=VERR_NEM_VM_CREATE_FAILED
VMSetError: Failed to get device handle and/or partition ID for 000000000174cc20 (hPartitionDevice=…0ad1, Last=0xc0000002/1)
```

读法：

1. **WHPX 是可用且已经工作的**——`NEM: Created partition` 说明 Windows Hypervisor Platform 分区创建成功，NEM 后端也确实以 Active 状态初始化了。所以"缺 WHPX / 需要启用 HypervisorPlatform 功能"这条假设**被日志否定**（我一度这样猜过，不要重复这个错误）。
2. 失败点是 `VidStartVirtualProcessor`：`dwErr=87`（`ERROR_INVALID_PARAMETER`），触发断言 `cbInput == sizeof(HV_VP_INDEX)`。这是 **VirtualBox 6.0.14 编译时假定的 WHPX IOCTL 参数尺寸与当前 Windows 构建的 API 不一致**。
3. `Last=0xc0000002` 是 `STATUS_NOT_IMPLEMENTED`，即取分区设备句柄这一步也没实现。
4. 旁证：`X2APIC is not supported by the WinHvPlatform API!` —— 6.0.x 对当前 WHPX 的适配本就是早期的。

**因此：在 VirtualBox 6.0.14 保持不动、且系统继续以 `hypervisorlaunchtype Auto` 启动的前提下，没有非侵入式解法。** 不是配置没调对，是 6.0.14 这版实现太旧。

### 10.3 让 guest 启动的两条技术方案（都属于所有者决策）

背景：§10.2 已确认失败点是 VirtualBox 6.0.14 与当前 Windows WHPX API 的参数尺寸不匹配。因此只有两条路能让 guest 真正启动。

#### 方案 A：启动时关闭 Hypervisor/VSM（`hypervisorlaunchtype Off`）

**机制**：Hypervisor 不加载后，VirtualBox 6.0 会走 HM/raw-mode VT-x 而不是 NEM/WHPX，从而完全绕开 6.0.14 的 WHPX 缺陷。这也是 H3C 官方安装说明建议的状态。

**实现**：已完全实现并验证过，工具在 `scripts/hcl_lab_boot.ps1`：
`-Action Create`（复制 `{current}`、只对副本设 `hypervisorlaunchtype Off` / `vsmlaunchtype Off`、追加到 `displayorder`、回读校验、先导出 BCD 备份）→ `-Action Arm`（在 `{bootmgr}`/`{fwbootmgr}` 间自动择一设置一次性引导 `bootsequence`，启动后自动清除，`default` 不动）→ `-Action Verify`（只读重启前自检）→ `-Action Disarm` / `-Action Remove` 回退。

**代价与风险**：

- 启动菜单会多出一个条目；选择该会话时 Hypervisor/VBS 防护与依赖功能不可用。
- `{current}` 与 `{bootmgr}` 的 `default` 自始至终未被改动（脚本每次都会断言）。
- 一次性引导只在**下一次**启动生效，之后自动消失。

**状态：已被设备所有者否决（2026-10-02）。** 理由是它改变系统启动配置、影响正常 Windows 开机体验。相关启动项与 `bootsequence` 已清除并独立复核（Disarm/Remove 均 `verified`；`osloader` 只剩 Windows 11 与 WinRE）。
**若要重启该方案**：需要所有者重新明确授权；重启前先跑 `-Action Verify`。

**回执**：`2704c0bf…`（Create）、`ae5381b1…`（Arm）、`cbee2b27…`（Verify）、`c7ad1fec…`（Disarm）、`95909812…`（Remove）、`bcd-after-cleanup.json`（复核）。

#### 方案 B：升级 VirtualBox 到 6.1+ —— **已做只读评估，结论：不能判定兼容，风险中等**

**机制**：VirtualBox 6.1+ 重写了 WHPX/NEM 适配，修正了 6.0.x 的 IOCTL 参数不匹配（即 §10.2 的 `cbInput == sizeof(HV_VP_INDEX)` / `dwErr=87`）。升级后**可以在 Hyper-V/VBS 继续运行的前提下启动 guest**，因此**不需要改动启动配置**——与所有者的明确意愿不冲突。这是唯一同时满足"不动启动配置"与"guest 能跑"的候选。

**状态：未执行、未授权。** 执行升级是机器级变更，必须先获得明确授权。下面是只读评估的结果。

##### ✅ 已排除的障碍

| 项 | 证据 |
| --- | --- |
| HCL **不校验** VirtualBox 版本 | `SimwareClient.exe` 中 `CheckVirtualboxInstall` 附近的字符串只有 `g_strVboxPath` + `path.join` + `VirtualBox.exe` + `VBoxManage.exe` + `isfile`，**没有版本比较**。日志里的 `Virtual Box version: 6.0.14` 是运行时读出来的。 |
| 那个 `6.0.14` 字面量不是硬编码期望值 | 它位于 `Core\Globals\Symbols.py` 的 docstring 示例文本里，旁边是 `hclVersion: 5.1.0` 与 `Windows-10-10.0.18362`——都是比当前安装更旧的示例，属陈旧注释。`SimwareWrapper.exe` 与 `H3C Cloud Lab.exe` 里根本没有 `6.0.14` 字面量。 |
| 安装路径假设与原地升级兼容 | 注册表 `HKLM\SOFTWARE\Oracle\VirtualBox` 的 `InstallDir = C:\Program Files\Oracle\VirtualBox\`，HCL 用的 `g_strVboxPath` 也是同一个路径。**原地升级不改路径**，符合 HCL 假设；并行安装则会破坏它。 |
| 绑定方式本身是版本自适应的 | HCL 用 **pywin32 晚绑定 COM**（`D:\HCL\pythoncom38.dll`），安装目录里**没有任何 `VBoxPython*.dll`**。`vboxapi` 走 `win32com.client.gencache.EnsureDispatch('VirtualBox.VirtualBox')`，包装器是**从已安装版本的类型库现场生成**的。 |
| HCL 用到的 COM 调用面是长期稳定接口 | 日志显示它只用 `findMachine`、clone、`setChipsetType`、内存/NIC/串口修改、`attachDevice`、`saveSettings`、`lockMachine` 这些核心接口，6.1 均保留。 |
| Extension Pack 与本场景无关 | HCL 的控制台走命名管道串口，不用 USB/RDP/VRDP。 |

##### ⚠️ 未排除的风险（**只读无法证明**）

1. **HCL 内嵌的 `vboxapi` 与 `VirtualBox_constants.py` 是 6.0.14 那一份**（已确认 SDK 的 `vboxapi/__init__.py:185` 与 HCL 回溯里的 `_CustomGetAttr` 完全对应）。若 6.1 改动 HCL 用到的枚举值或接口签名，可能出错。**必须实际安装才能验证。**
2. **stale `gen_py` 缓存**：`C:\Users\w8p1p\AppData\Local\Temp\gen_py` 已存在（4 个文件）。升级后若不清除，pywin32 可能继续用 6.0.14 生成的包装器。**升级后必须删掉该目录。**
3. **VM 配置格式是单向升级**：当前 `.vbox` 为 `version="1.16-windows"`。6.1 会把 VM 配置改写成新格式，**之后 6.0.14 可能读不回来**——所以"升级后不行再降级"对既有 VM **不完全可靠**。升级前必须整目录备份 `C:\Users\w8p1p\HCL VMs\`。
4. **回退资产缺失**：`D:\` 与 `Downloads` 下**都没有 VirtualBox 6.0.14 安装包**，降级需要重新获取。
5. **目标版本存在取舍**：6.1.28+ 修 Windows 11 主机问题，但 HCL 的 COM 绑定是 6.0 时代的；7.0 的 WHPX 共存最成熟，但 COM API 变动更大，对 HCL 更危险。**建议若做，选 6.1 系列最新版而不是 7.x。**
6. **外部证据不足以定论**：工单标题为 ["No VM will start on Windows 11 host => fixed in 6.1.28"](https://www.virtualbox.org/ticket/20536)，但另有用户报告 [6.1.26 升到 6.1.28 后出现同样的 `E_FAIL (0x80004005)`](https://superuser.com/questions/1684788/virtualbox-fails-to-start-vm-after-upgrade-from-6-1-26-to-6-1-28-with-result-cod)。本机 `virtualbox.org` 与镜像域名都解析到非公网 IP，**未能读取工单正文**，因此这条只能作为线索，不能作为结论。

##### 评估结论

- **"HCL 会不会因为版本不对而拒绝运行"——已排除，不会。**
- **"装了 6.1 之后 guest 能不能起来"——无法只读证明**，取决于 6.1 的 WHPX 实现能否修掉 §10.2 那个参数尺寸问题，以及 HCL 那份 6.0 时代 `vboxapi` 是否仍匹配 6.1 的类型库。
- 因此这仍是一个**需要所有者授权的、带真实回退风险的机器级试验**，而不是一个"可以先做做看"的低风险改动。

##### 若决定执行：最小风险步骤与验收

**准备（全部只读，可先做）**

1. 记录基线：`VBoxManage --version`、`list vms`、`list systemproperties`（已存 `hypervisor-report-20261002.json`）。
2. **整目录备份** `C:\Users\w8p1p\HCL VMs\`（含 `Simware_Base` 与既有拓扑）。
3. 拿到 VirtualBox 6.0.14 安装包（当前磁盘上没有）作为回退资产，并记录 `D:\HCL\vboxapi` 的可用性（该目录在 exe 内，只能记录其来源）。
4. 记录 HCL 侧基线：`hcl_bridge_status` 的 `1.0.0&6.0.14`、隔离副本的 `inspect` 结果、`create_topology` 返回 `100`。

**执行**：原地升级到 6.1 系列最新版 → 删除 `%TEMP%\gen_py` → 以管理员重启 VBoxSVC。

**验收（缺一不可）**

1. `VBoxManage startvm` 能启动一台测试 VM 并进入 guest；
2. HCL 打开隔离副本 → 新增/删除设备 → 保存回读仍然成功（现有已验证能力不退化）；
3. `hcl_backend_topology` 的 `create_topology` 仍返回 `errorCode=100`；
4. HCL 日志中不再出现 `VERR_NEM_VM_CREATE_FAILED`；
5. 既有 `topo1`/`topo77` 拓扑的 VM 配置仍能被 HCL 读取（格式升级未破坏）。

**失败判定与回退**：任一条不满足即视为不兼容；此时回退到 6.0.14 并恢复 `HCL VMs` 备份。**注意第 3 条风险**：若 6.1 已改写 VM 配置，回退未必能完全复原。

**证据文件**：`work/feasibility/dsh-20261001/vbox-version-scan.txt`、`vbox-version-context.txt`、`work/feasibility/lab_boot_20261001/hypervisor-report-20261002.json`。

#### 方案 C（当前默认）：接受 guest 不可用，推进 D0/D1

不需要任何授权，**33 项不受影响**，见 §10.4。在 A/B 未决期间这是唯一可推进的方向。

### 10.4 关键事实：这个阻塞只影响 61 项里的 24 项

按 HANDOFF §5 的分类，**D0 离线 14 项 + D1 后端控制平面 19 项 = 33 项完全不需要 guest 启动**。其中 D0 还有 11 项没做、D1 还有 18 项没做。所以：

- P0 契约硬化、P1 全部离线层、P2 控制平面其余部分、P3 注释与 relay，**都不受本阻塞影响**。
- 受影响的只有 D2 的 24 项 CLI 家族（`apply_*`、`read_vlans`、`verify_connectivity`、`deploy`、`backup_config` 等）与仿真 3 项。
- 不要在报告里把"guest 起不来"写成"项目无法继续"。

### 10.5 仍然成立的两条经验

- 本机 `sudo` 处于**强制新建窗口模式**（`sudo config`）：`--inline` 被拒绝，提权进程 stdout 不回调用终端。**凡提权动作都要用"写文件回执"取结果**，不要依赖管道输出。
- `bcdedit` 非提权下**无法枚举** `{current}`。此时"读不到"**不是**"没进实验项"——`hcl_lab_environment.ps1` 已改为返回 `verdict=unknown_cannot_read_bcd`，不要再把无法观测当成否定结论。

> **备份是机器本地的**：`bcd-before.bak` 在 `work/` 下，`work/` 被 Git 忽略，清理它会丢。它只用于灾难恢复，日常回退用 `Remove` 即可。

---

## 11. 未验证 / 危险区

**未验证**

- **方案 B 的两处无法只读证明**：HCL 内嵌的 6.0.14 版 `vboxapi`/`VirtualBox_constants.py` 是否仍匹配 6.1 的类型库；以及 6.1 升级后 guest 是否真能启动。二者都必须实际安装才能验证（详见 §10.3）。
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
- ~~`errors[]` 形状不一致：语义错误是 `{code,message}`，结构错误是 pydantic 原始 `{type,loc,msg,url}`，没有 `code` 键~~ → **已在 `dsh-2` 统一**：结构错误也带 `code: "invalid_plan_structure"`，原始 pydantic 形状移入 `detail`。
- ~~损坏工程（`device_id = abc`、`x = not-a-number`）会以**工具错误逃逸**而非业务 `rejected`~~ → **已在 `dsh-2` 修复**：`project.py` 的 `_field_integer`/`_field_number` 让这些形状统一返回业务 `rejected`（非有限坐标也拒）。其余形状（缺 `[vbox]`、两个 `[vbox]`、缺 `device_id`、重复字段、非对称链路、非 UTF-8）本来就正确拒绝。
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
6. **P4 / guest 启动**：**暂时无解**（启动配置方案 A 已被否决；方案 B 只读评估已完成但需授权才能执行）。不要再去碰 BCD。在 B 未决期间，**可以零授权先做 B 的"准备"部分**：记录 `VBoxManage` 基线、**整目录备份 `C:\Users\w8p1p\HCL VMs\`**、找到 6.0.14 安装包作为回退资产（当前磁盘上没有）。这些都是只读或纯备份，不改变系统；真正的升级动作要等明确授权。其余精力放在 1–5 项。

### 改动纪律（请延续）

- 每个新动词必须标注 `evidence`（`verified`/`observed`/`inferred`）与是否 `writes`。
- 写动词默认 `invocable=False`，除非字段语义有据可依。
- 每个"成功"都要有 `verified_scope`，并且**不得跨层推断**：命令被接受 ≠ guest 启动 ≠ 配置下发 ≠ 网络连通。
- 任何对外部世界的成功声明都要附回执路径；回执进 `work/`（被 Git 忽略）。
- 只提交到 `dsh-2` 分支（`dsh` 已被所有者删除；历史提交自 `3bbccdb` 起完整保留在 `dsh-2`）。

---

## 14. 当前阶段状态与待决事项

**阶段性完成（2026-10-02，`dsh-2`）**

- 控制平面第一层：动词注册表、写总开关、帧解析、持久连接会话、命名管道控制台、4 个 MCP 工具 —— 已实现并**对真实后端验证**。
- P0 契约硬化前两项：结构错误统一 `code`；损坏工程不再以工具错误逃逸。
- 文档收敛为 `HANDOFF.md` + `README.md` 两份。
- 本机测试基线 **66 项通过**（1 项因账号无 symlink 权限 skip）。
- guest 启动阻塞的**根因已定位**（§10.2），且已确认"缺 WHPX"是错误假设。
- 方案 B 的**只读兼容性评估已完成**（§10.3）：HCL 不校验 VirtualBox 版本、路径与绑定方式兼容；`vboxapi`/VM 配置格式升级属只读不可证。执行仍需授权。

**待所有者决定**

| 事项 | 说明 |
| --- | --- |
| 方案 A 是否重新授权 | 见 §10.3；当前被否决，条目已清除 |
| 方案 B 是否执行 | **只读评估已完成，见 §10.3"方案 B"**：HCL 不校验版本、路径与绑定方式兼容，但 `vboxapi` 与 VM 配置格式升级属只读不可证；结论是"带真实回退风险的机器级试验"，需授权 |
| 是否开工 P1 离线层 | 见 §9；D0 的 11 项零阻塞、可离线回归 |

**不要做的事**：不要为了"让 P4 看起来有进展"再去碰 BCD；不要把 guest 起不来写成项目无法继续（33 项不受影响）。


## 15. 2026-10-02：使用者授权分支内试验后的更新

本轮在 **dsh-2** 实际执行官方 SDK 声明对比、安装资产校验、完整 VM 备份和软件回归；结果见 [方案 B 试验报告](docs/plan-b-sdk-assessment.md) 与 [验证记录](docs/plan-b-verification-20261002.json)。

30 个选定接口成员中 29 个声明相同；launchVMProcess 第三参数从字符串变为字符串数组，MachineState 部分快照枚举和 IMachine UUID 也改变。因此 §10.3 中“核心 COM 接口长期稳定 / 升级可直接让 guest 启动”不能作为兼容性保证，实际 HCL 参数转换、COM 注册和 WHPX guest 启动仍未验证。

6.1.50 候选包和 6.0.14 回退包均已下载，官方哈希匹配，Oracle 签名 Valid；52 个现有 HCL VM 文件及 VirtualBox.xml 已备份并核对字节一致。恢复未测试。原安装仍为 6.0.14r133895，安装器未执行。

本轮回归 **69 项，68 通过、1 权限相关跳过**。本分支仍来自 1200f30，没有包含 Codex 的 0.5.0；旧的 15 工具/3 资源和 P0/P1 说明仅属于 dsh-2 的旧应用基线，不能用于评价 Codex 的 39/6、138 项测试。

授权仅限分支内操作。共享 VirtualBox 的驱动、COM 和已有 VM 配置不受 Git 分支隔离；未额外授权前不安装、不清缓存、不修改 BCD 或系统安全功能、不启动真实 guest。当前结论仍为 **方案 B 尚未证明可行**，full_live_gate_passed=false。


## 16. 2026-10-02：所有者追加授权后，VirtualBox 原地升级已完成

使用者对“本机原地升级到 6.1.50，不修改 BCD/安全设置、不自动重启，guest 验收由使用者触发”的请求明确回复 **允许**。这是一次性机器级升级授权，不是对未来系统变更的通用授权。此前仅限分支内的限制在这一次安装上被明确扩展。

- 官方签名 x64 MSI 已安装，退出码 **0**；当前 VBoxManage 为 **6.1.50r161033**，路径仍 C:/Program Files/Oracle/VirtualBox。安装器未要求重启，未自动重启。
- 只读动态 COM 回读 version=6.1.50、APIVersion=6_1；findMachine 能找到原 Simware_Base，UUID 不变，状态 powered off。没有调用 launchVMProcess 或 HCL 自带 SDK 启动流程，也没有清理共享 gen_py 缓存。
- 安装前后 BCD 全量枚举相同、启动会话相同，Hypervisor 继续启用。52 个原 VM 文件在安装及 API 读取后哈希未改变。备份与 6.0.14 回退包保留，恢复未试验。
- VBox 驱动当前回读见新记录；旧后端、失败日志与 SDK 对比仍是各自历史层面的证据，不能据安装成功改写为运行通过。

安装回执、日志、驱动与 COM 读回路径见 [机器升级记录](docs/plan-b-host-upgrade-20261002.json)。目前 **只有安装和基础 API 层通过**；HCL 的旧 SDK 参数转换、GUI 打开/保存、真实 guest、控制台配置、网络连通性与回退均未验收，full_live_gate_passed=false。§10 的“当前安装 6.0.14 / 方案 B 未执行”从此仅代表升级前历史状态。

下一步由使用者打开隔离阶段工程并手动启动其中一台设备，再提供本次控制台与 VBox/HCL 日志以核对。不要启动 Simware_Base 或原工程做实验，不自动启动 guest，不因失败而关闭安全功能、重建启动项或重放启动。任何超过一分钟的真实验收仍由使用者触发。


## 17. 2026-10-05 收口：方案 B 单设备 GUI 启动实测及清理

使用者明确允许 Computer Use 模拟 GUI 操作；管理员 HCL 窗口无法由当前工具可靠输入后，使用者手动关闭，并授权普通权限重新打开。实际观察发生于 2026-10-02，2026-10-05 继续时没有重跑成功的启动试验，仅完成状态复核、恢复和交接记录。详情见 [GUI 实测记录](docs/plan-b-gui-probe-20261005.json)。

### 已取得的新证据

1. 首次打开单台 MSR36-20 副本失败，GUI 提示“创建设备 Gui61Router 失败”，后端返回 206。HCL 的 Python 3.8 gen_py 缓存仍用旧 FindMachine/CreateMachine DISPID（1610743850 / 1610743847），6.1 实际为 1610743851 / 1610743848，导致类型/参数数目错误。这不是生成工程格式失败，厂商日志已通过 .net 校验。
2. 保存首个失败回执后关闭 HCL，仅把 VirtualBox 那一个类型库的 .py 和 .pyc 共两份旧缓存搬入私有备份，不删除整个 gen_py，也不修改 HCL 二进制。HCL 重开后自行生成新版缓存。
3. 新副本 Gui61_870c0dbe 成功在 GUI 中打开，唯一设备 Gui61RouterB 创建成功；VirtualBox 注册 UUID 为 17cc6f4c-9671-4ec0-b5f6-fe9c8794be04。2026-10-02 22:09:26–22:09:30 GUI 启动成功，后端请求 20 返回 100；VBox.log 显示 NEM Active、RUNNING 和硬盘启动。Guest 画面进入自动配置尝试，单台无链路场景没有可用接入网络。Hypervisor 仍启用，未改 BCD/安全设置。
4. 原生命名管道读取返回 PermissionError；没有任何有效 CLI 回读，不确认其原因是 ACL、占用、管理员上下文或共享模式。不要把这个失败删掉，也不能由绿色图标/VM RUNNING 推断配置或网络通过。串口文件当时也未取得有效可读内容。
5. 2026-10-02 22:20:33 通过 GUI 停止该设备，观察到原先没有记录的 `stop 6 0`、请求 22 返回 100。第二个参数语义仍未证明；此观察不自动开放 MCP 的 stop，也不增加 implemented。

### 原始状态恢复与当前环境

HCL 在初始化/正常关闭过程中清理了共享 HCL VMs 下的旧运行时目录。不能把“工程副本不同”当作“运行时 VM 目录隔离”——本次 GUI 仍使用 topo1，与旧缓存命名空间相同。首个失败后曾恢复过一次；成功试验结束后又有 47 个旧文件缺失。完整 52 文件备份始终保留。

2026-10-05 确认 HCL 与 guest 均未运行后，仅恢复缺失的 47 个文件，不覆盖已有文件；52 个原文件哈希全部一致。原工程 .net 仍匹配历史 CCC821A5…A785570。HCL 关闭还移除了原 Simware_Base 注册，因此通过 registervm 恢复其原 UUID 7ac3bddb-1356-4121-b70a-fd14a8bd8a94；注册后再次核对 52 文件一致，没有启动原 Base。当前 VBoxManage 列表仅原 Simware_Base，runningvms 为空；VirtualBox 保持 6.1.50。

HCL 关闭日志还有 closeAllDisk 针对不同厂商镜像的重复 UUID 警告。没有改变厂商镜像 UUID 或文件；这只是关闭阶段观测，混合型号创建/无线兼容性仍未测试，不能据此宣称支持或不支持所有型号。

### 结论与后续门槛

**方案 B 已在本机证明“修正旧缓存后，单台 MSR36-20 可由 HCL 创建并启动进入 guest 系统阶段”。** 不等于全版本/全型号兼容，不等于原生 CLI 已可独占回读，更不等于 OSPF/DHCP 或无线闭环完成。full_live_gate_passed=false；本轮没有配置下发、网络验收、BCD 写入、安全设置变更、重启、push 或发布。

后续优先解决实际控制台的权限/占用/共享语义和 runtime VM 目录隔离，再考虑三路由器验收；保留两次 GUI 试验及失败读取回执。不得终止别人的 PuTTY/MultiCC，也不得关闭系统安全功能。真实长时验收仍由使用者明确触发。dsh-2 仍未合入 Codex 0.5.0；本次没有增加工具数量或上游 implemented 计数。


## 18. 新会话的问题清单与排查顺序（2026-10-05）

**新会话先阅读 §17 和本节，再查看解决方案。** 本节不授予新的系统修改、镜像修改、设备启动或长时测试权限。当前只有单台 MSR36-20 创建/启动进入系统阶段的证据；CLI、配置、连通性和无线均未完成。详细过程与回执集中在 [GUI 实测记录](docs/plan-b-gui-probe-20261005.json)，避免重跑已通过的启动来掩盖下面的缺口。

### P0：工程副本没有隔离 HCL 运行时目录（尚未解决）

- 条件：GUI 打开不同的阶段目录，仍分配运行拓扑名 topo1，使用同一用户的 HCL VMs。初始化/正常退出会清理旧目录和 Simware_Base 注册。
- 实际影响：本次出现 47 个历史运行时文件缺失，发生过两次恢复。最终 52 文件哈希全部一致，原 Base UUID 与注册恢复、原工程 .net 哈希不变，当前无运行 guest。恢复只证明文件/注册，不证明设备配置恢复或 VirtualBox 降级回退。
- 先查：HCL 的运行时根、拓扑名分配、tryCleanLeftVMs/normal_close 的清理边界。只读检查是否有受支持的隔离入口；没有证据前，不猜启动参数、修改用户环境根或直接调用未知 create/delete 动词。
- 修复验收：一次打开/创建/启动/停止/退出只触及本次独立 VM 命名空间，历史注册、磁盘及回执保持不变。仅 .net/workingdir 分开不足以通过。解决或明确保护这项之前，不开展混合型号或三路由器批量实测。
- 证据：GUI 实测记录的 cleanup；本机 `work/feasibility/plan-b-20261002/gui-runtime-restoration-1.json`、`cleanup-final-pointer.json`、`registration-restoration-20261005.json`；完整备份路径在 `backup-receipt.json`。

### P1：原生命名管道读取 PermissionError（尚未解决）

- 条件：唯一测试 VM topo1-device6 已 RUNNING，普通权限 HCL 会话存在 SimwareMultiCC；原生 ConsoleSession 尝试打开实际日志给出的管道，返回 PermissionError，收到 0 字节，未发送任何控制台命令。
- 不确定点：CRT 的 PermissionError 没有保存底层 Win32 错误码，不能区分真正访问拒绝与 busy/share 情况。管理员上下文、ACL、已有客户端和单实例语义都是候选，尚未定因；不要直接说“管道不可用”或“管理员就能解决”。
- 先查：实际 .vbox UART 角色、管道创建/连接时序、服务与客户端进程、原生错误码。记录 ACL/占用等观察，不终止别人的 PuTTY/MultiCC，不改 ACL/安全设置，不并发消费同一个流。
- 当时 UART0 是 RawFile 指向阶段工程 SerialFile/Gui61RouterB.txt，UART1 是 server=true 的 HostPipe；串口文件也曾访问拒绝，后被 HCL 清理，不能把它说成已取得的 CLI 回读。
- 修复验收：绑定本次设备身份，取得独占、有回显/提示符归因的真实只读输出；陈旧、截断、超时和占用仍拒绝。VM 图标绿色、BIOS、OS 自动配置画面均不替代这个合同。
- 证据：`work/feasibility/plan-b-20261002/gui-attempt-2/boot-console-receipt-2.json`、`running-topo1-device6.vbox`、`running-VBox.log`、`running-ui.txt`。首个 boot-console-receipt.json 记录的是探针误把 PipeLease 当上下文管理器的错误，不是产品管道失败，须与第二份分开。

### P2：关闭阶段出现厂商镜像重复 UUID（尚未解决/影响未确认）

- 位置：SimwareWrapper 的 closeAllDisk 调用 OpenMedium，部分 ap/diy/f1090 等镜像与已登记的 msr36_b75.vmdk 报同一 UUID 冲突。
- 目前只观测到关闭阶段警告，没有混合型号创建结果，也没有证明这是升级新引入的回归。应先与 6.0.14 历史日志、镜像头及媒体登记信息作只读对照。
- 不修改厂商原镜像 UUID，不批量 unregister/delete 原介质，不据此猜测 AC/AP 一定可用或不可用。若方案需要修改独立副本，先明确原件保护、引用关系和回退方式。
- 证据：`gui-attempt-2/final-wrapper-log.txt` 及 GUI 实测记录 known_shutdown_warning；厂商文件没有被补丁化。

### 已解决但必须延续的注意项

- **旧 COM 生成缓存**：确认过 FindMachine/CreateMachine 旧 DISPID 与 6.1 不符；只隔离 VirtualBox 对应类型库在 Python 3.8 下的两份 .py/.pyc，HCL 自动重建后创建设备成功。旧/新缓存与哈希已保留；不要清空整个 gen_py 或改 HCL 二进制。证据为 `cache-quarantine-receipt.json`、`gui-attempt-1/result.json`、`gui-attempt-2/regenerated-typelib-cache.py.txt`。
- **管理员 GUI 输入边界**：管理员 HCL 的鼠键输入未产生可靠效果；用户手动关闭并允许普通权限重开后继续。用 Computer Use 当前返回的窗口与新截图；Qt 模态中 UIA 焦点文字曾与实际文件名输入框不一致，必须核对输入实际位置和结果，不盲打、不绕过权限隔离、不用 PowerShell UIA 替代。
- **新 stop 观察**：GUI 实际发出 stop 6 0 并收到 100，仅记录这一次形状；第二参数语义未补齐，不能自动开放 MCP stop。

### 新会话起点、权限及交付要求

1. 先复核实际 branch/HEAD、运行中的 HCL/guest、VirtualBox 版本和备份存在性。2026-10-05 收口时 dsh-2 为 c9b4eca，源代码/工具仍是旧 DSH 基线；本次下一提交只更新交接。Codex 工作区为 a6a4f78、0.5.0、39 工具/6 资源，两分支未合并。不要把 dsh-2 的 69 项测试当作 Codex 的 138 项回归。
2. 第一轮以只读定位与修复设计为主：先 runtime 隔离，再控制台错误归因，最后媒体 UUID/混合型号。优先利用已有回执；work/ 被忽略，换机器或新工作区可能缺失，须明确报告。
3. 原 Windows 启动项方案已撤销，BCD/安全功能/自动重启不在后续操作范围；一次性升级授权已经执行完，不能解释成允许继续更换版本或改镜像。Computer Use 的历史授权仅记录已经完成的这次试验；新的设备操作依照新会话用户指令和适用规则执行。
4. 保留每次失败；新复测使用新工程、目录和 operation_id，不覆盖或改写已有负面结果。逐层报告“发现 / 修复 / 软件验证 / 真实回读”，全绿之前 full_live_gate_passed=false。

### Suggested skills（面向问题排查）

- `api-and-interface-design`：控制台输入/输出、错误码和证据合同。
- `tool-failure-handling`：独占租约、超时、失败停止与恢复边界。
- `code-review-and-quality`：具体修复差异的独立审查。
- `computer-use:computer-use`：仅在新会话明确需要并允许 GUI 操作时使用。
- `handoff`：收口时更新已验证范围和剩余问题，引用原始回执。

## 19. 2026-10-05：本机标准账号 MCPHCLLab 已授权创建

使用者在账号审阅后明确指定账号与测试密码，Codex 在 8a46 独立工作区执行了本次创建。MCPHCLLab 已启用；独立读回确认属于 Users、不属于 Administrators。密码经同 owner 的受保护内存管道交给 Windows 提权助手，未写入 Git、命令行参数或工作回执；没有修改密码策略。

实际账号 SID、唯一 description 及未来按 SID 停用/删除的创建回执位于：
`C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/work/account-creation-20261005/748abd1c1434409d8b9ab95e0f37c68c/account-receipts/3a42945c83794fcabde4763c5def3e8c/result.json`。

目前 profile_count=0、预计用户配置目录尚未生成；没有自动登录、初始化 HCL 或启动 guest。此授权仅扩展到账号创建，不是对原镜像、系统启动、安全功能或真实长时设备验收的通用授权。

创建后原 52 文件的清单/元数据、VM 描述符哈希和 VBox 注册哈希与创建前一致；未重复全量读取大磁盘字节。原工程 .net 仍为 CCC821A5…A785570，原 Base UUID 不变，runningvms 为空；VirtualBox 仍为 6.1.50。

最新纯软件包已校验并放到 `C:/Users/Public/Documents/MCP_HCL_Lab_20261005_Topology`，不含厂商程序、镜像或原用户资产。0.5.0 core wheel SHA256 为 c4d331497d87288b2a0e3af29053d7ccc77165349de8fca18d382768230118ab；该源码位于 8a46，**仍未合入 dsh-2**，不能用 dsh-2 旧测试数或接口面评价它。

下一步由使用者手动首次登录 MCPHCLLab，生成真实 profile，再核对新 SID、VBox 注册、运行时根、共享端口/管道及厂商清理边界。账号创建不证明 runtime 隔离；§18 的 CLI、媒体和完整生命周期门槛仍未通过，full_live_gate_passed=false。

## 20. 2026-10-06：独立工作区软件包更新指针

8a46 独立工作区加入运行态查询、限定ACL/VLAN、保存/恢复、跨设备VLAN及ACL删除，最新发现面46工具/6资源。旧完整软件回归238项与后续runtime/VLAN检查保留，最新删除只运行8项专项与3项发现/门控依赖，没有重跑全部历史软件面。不是dsh-2或真实HCL测试结果。最新记录在 C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/docs/acl-removal-20261006.md。

最新准备包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_NatModes，wheel SHA256 65bc0c3b41bdabbddd5c1cdcd0782f17621f5de73d6b9f78dbe5907895e1ff41，45个包文件匹配源码，复制后清单通过；46/6发现面和默认门控通过。旧包保留，dsh-2源码未合入独立工作区未提交改动。真实固件/隔离/流量/重启和完整等价未通过，full_live_gate_passed=false；不能据软件结果删除仍待真实测试的实验账号。

用户后续明确授权Codex后台执行只读采集，已在真实MCPHCLLab SID1006会话取得profileC:/Users/MCPHCLLab、runtime文件0/注册0、无HCL/guest/错误的初始基线；临时配置已卸载，主账号权限未扩大。两次失败和实际第三次操作见 C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/docs/lab-profile-observation-20261006.md。没有改执行策略、启动HCL/guest或切换桌面。下一步是必要生命周期/CLI隔离门槛，空初始空间仍不证明厂商清理边界。

后续仅检查新增环境路径，发现home组合随公共工作目录补齐，现已把后台子进程WorkingDirectory设为CIM登记的真实实验profile并按SID复核；USERPROFILE和home组合均为MCPHCLLab，策略Restricted未改，没有手工覆盖环境变量。PID39184已退出/profile未加载，旧资产结果沿用。记录在 C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/docs/lab-environment-20261006.md；仍未启动HCL/guest或证明实际清理范围。

用户明确：账号用于测试，必要真实测试完成后停用并按创建SID/唯一标记删除；只做必要测试，沿用有效结果，不做重复或多余测试。此条件清理已授权，不再索取同一授权；用户目录、VM和证据保留。账号清理未执行，仍是完整交付的后续要求。授权不扩展到系统启动、安全功能、共享VirtualBox或自动长时验收。


最新软件补充NAT地址池及PAT/no-pat生成，17项专项及2项stdio/Schema依赖通过；46/6不变，没有离散NAT应用/删除或真实转换结论。说明在8a46/docs/nat-modes-20261006.md。

用户明确空闲、允许接管单设备生命周期；启动前保存原52文件完整字节及保护清单。跨账号宿主与文件权限两个失败保留，未启动guest；改Windows PowerShell5.1及同字节可读输入后实际SID/环境通过。H3C启动器requireAdministrator导致UAC，当前待用户手动取消，尚无HCL/guest进程。正常权限客户端入口仍待确认，不输入管理员凭据/修改安全设置或manifest。当前记录8a46/docs/isolation-trial-execution-20261006.md；账号仍待必要真实测试结束后按SID删除，full_live_gate_passed=false。


## 2026-10-06：测试交由 DeepSeekHarness 下的 DeepSeek

使用者明确将测试交给 DeepSeekHarness 下的 DeepSeek。Codex 已停止测试；未打开审阅工程、创建设备或启动 guest。单设备生命周期、CLI/配置/网络及完整上游等价仍未通过，full_live_gate_passed=false。

交接稿：C:\Users\w8p1p\AppData\Local\Temp\MCP_HCL_DeepSeek_Test_Handoff_20261006_ccf4b7d7.md。当前收尾时无 HCL/guest/采集进程，实验 profile 未加载；原52文件元数据/描述符及注册哈希与恢复后一致。控制器与观察器期限失败保留。最新事实见独立工作区 docs/isolation-trial-execution-20261006.md；必要测试结束后按创建 SID 停用并删除账号、保留 profile/VM/证据的条件授权继续有效，账号暂留供接手测试。

## 2026-10-06：独立 NAT 软件事务稿，测试仍由 DeepSeek 接手

Codex 继续软件实现，新工作区 C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL 从8a46已交接源码快照复制，detached9963ddc、改动未提交。8a46 tracked快照哈希复核未变。本次新增hcl_apply_nat/hcl_remove_nat、参数Schema、编号/池名映射、范围回读与共享引用/恢复/重复操作保护；没有执行单元、模拟、MCP调用或guest测试。声明面预计48工具/6资源，SDK发现及行为待DeepSeek。

候选包 C:/Users/Public/Documents/MCP_HCL_NAT_Transactions_Untested_20261006，wheel SHA256 bc0ff83620fce4c6b0ebd5c2326a5fae256b63bef18605dc8e1502eaed5634c9。只完成语法解析、Schema制品、构建及48包文件字节核对，不是功能通过；没有安装或启动。旧包和失败保留。

合同/待验项见新工作区 docs/nat-transactions-20261006.md、docs/nat-transactions-delivery-20261006.json。IOS ingress-role及池mask的数据面等价未实现/验明，上游12/46/3和full_live_gate_passed=false保持。E:/MCP_HCL的dsh-2仍是旧源码，没有合入或push。测试账号供DeepSeek后续必要真实测试使用，测试结束按创建SID删除、保留数据的要求保持。
## 2026-10-06：接口调优软件实现稿，未执行测试

同一nat-transactions独立软件工作区新增hcl_apply_interface_tuning，预计声明面49工具/6资源。保留上游字段，当前实现bandwidth/OSPF标量和认证设置的限定事务；不执行尚无接受映射的clock_rate/delay完整请求。SecretStr/回执遮蔽与密文shape层的partial结论纳入；密钥值、邻居与完整等价仍未验证。细节见该工作区 docs/interface-tuning-20261006.md 和交付JSON。

候选包 C:/Users/Public/Documents/MCP_HCL_Interface_Tuning_Untested_20261006，wheel SHA256 e262a5f550d43c894fb4570dca46c61d0cee83cec199f244db9c35e38c39b6e3，49包文件字节匹配。只做语法/Schema/构建/字节核对，没有单元、模拟、MCP发现/调用、guest或网络测试；测试由DeepSeek。未安装/提交/合并/push。旧8a46测试快照和候选包保留，原12/46/3计数及full_live_gate_passed=false不变。
## 2026-10-07：STP/端口安全软件稿，测试仍由 DeepSeek 执行

独立nat-transactions工作区加入hcl_apply_stp/hcl_apply_port_security，预计声明面51工具/6资源；未执行单元/模拟/stdio/MCP发现或guest/流量测试。严格DTO、差异回读、VLAN压缩保护、全局BPDU/认证重置和学习状态影响检查加入。旧PVST、IOS root-primary动态优先级算法、protect/restrict及实际根桥/学习/入侵行为仍不完整/未验证，对应上游行仍planned。说明与必要验项见 docs/switch-security-20261007.md（在独立软件工作区）。

候选包 C:/Users/Public/Documents/MCP_HCL_Switch_Security_Untested_20261007，wheel SHA256 239a9f37bf7c8a3202c886ac9a6d8bd7bfac750c98319bc5e34520df0ce2f27f，50包文件与源码字节一致。只证明语法、Schema、构建及包字节；不证明51接口发现/功能。旧测试快照与包保留，未安装、未提交/合并/push，原12/46/3及full_live_gate_passed=false不变。账号清理仍待必要真实测试结束，按创建SID删除并保留数据的授权有效。

最新DeepSeek测试入口为 C:/Users/Public/Documents/MCP_HCL_DeepSeek_Test_Handoff_20261007_51tools_93fe891a.md，临时原件同名位于 C:/Users/w8p1p/AppData/Local/Temp/。它更新待测源码/候选定位，并引用旧交接的真实环境证据；旧交接不再代表最新软件版本。此轮仅整理交接、复核候选wheel哈希及既有冻结补丁，不执行测试，也未自动发送给DeepSeek。

## 2026-10-07：拓扑差异/健康软件稿与53声明交接增补

独立nat-transactions软件工作区新增hcl_diff/hcl_health_check，预计声明53工具/6资源。读取绑定的阶段guest接口，报告地址差异/重复地址和未知观察；原生全设备/线缆清单、IPv6及路由域读取仍未完成，同步/健康不返回伪通过。详见该工作区 docs/reconciliation-20261007.md。两行仍planned，12/46/3和full_live_gate_passed=false不变；E盘旧源码未合入。

新候选 C:/Users/Public/Documents/MCP_HCL_Reconciliation_Untested_20261007，wheel SHA256 20c2740e19b9e056a7378653b5abe5149a02621c5a538d2f86e1f3f8e7437894，51包文件字节匹配。只做语法/Schema制品、构建、包字节与tracked空白检查，没有功能、单元、模拟、SDK发现/调用或真实测试，也未安装/启动、提交/合并/push。旧候选/回执保留。

最新交接增补为 C:/Users/Public/Documents/MCP_HCL_DeepSeek_Test_Handoff_20261007_53tools_583747bc.md；临时原件在用户Temp同名文件。测试仍由DeepSeek执行，完成全部必要真实测试后按原创建SID删除MCPHCLLab、保留profile/VM/证据的授权保持。

## 2026-10-07：53声明的IPv6/地址域观察软件更新

独立nat-transactions工作区补充IPv6详细地址观察及重复IPv4才触发的VPN列读取，健康新增include_ipv6=false。格式、DAD/生命周期/anycast、部分失败和必要待验项见该工作区 docs/address-observation-20261007.md。完整原生设备/线缆库存入口仍未确认，Wrapper只读静态标识不能代替分派协议；没有开放未知命令或执行厂商代码/原生请求。

最新候选 C:/Users/Public/Documents/MCP_HCL_Address_Observation_Untested_20261007，wheel SHA256 5d8b6ba7573d4db89a385f62ce5880d46a50e545d0a22472698b63ef9280a943，52包文件字节匹配，预计53工具/6资源不变。只做语法/Schema/构建/包字节和tracked空白核对，功能/SDK/原生测试仍0。旧候选/回执保留，E盘旧源码未合入；12/46/3与full_live_gate_passed=false不变。

DeepSeek最新增补为 C:/Users/Public/Documents/MCP_HCL_DeepSeek_Address_Readback_Handoff_20261007_5d8b6ba7.md。必要真实测试结束后按SID删除账号并保留profile/VM/证据的要求保持，本次未清理仍待测试的账号。

## 2026-10-07：GUI身份/运行时前置保护软件更新

独立nat-transactions工作区的open/save加入SID/非提权令牌、进程/默认监听者、调用者目录、空运行时/注册、内存许可及账号共享GUI锁检查，53声明不变。HCL/Wrapper内部环境、GUI实际后端连接、清理边界和原生全设备/线缆库存仍未验证；不能把保存文件提升为全拓扑原生证明。合同与必要验项见该工作区 docs/gui-identity-20261007.md。

最新候选 C:/Users/Public/Documents/MCP_HCL_GUI_Identity_Untested_20261007，wheel SHA256 f4c8bf3fd4bf10ad52691b78d0b87018122f0d8c05e31f73c72401ee63ed08fe，54包文件字节匹配。仅语法、C#助手编译、构建/字节与tracked空白核对，没有调用采集器/令牌方法/GUI，没有功能/SDK/原生测试。E盘旧源码未合入，12/46/3及full_live_gate_passed=false不变。

DeepSeek最新交接 C:/Users/Public/Documents/MCP_HCL_DeepSeek_GUI_Guard_Handoff_20261007_f4c8bf3f.md。旧候选/证据保留，必要真实测试后按SID删除MCPHCLLab并保留profile/VM/证据的条件授权保持。

## 2026-10-07：配置安全审计软件更新，54声明

独立nat-transactions工作区新增hcl_audit_security，预计54工具/6资源，输出配置姿态分类/诊断，密码/密文/原始控制台及配置哈希抑制尚未验收。Comware与Cisco特权/加密/启动旁路及算法的完整等价仍缺，secure不返回true。详见该工作区 docs/security-audit-20261007.md。

最新候选 C:/Users/Public/Documents/MCP_HCL_Security_Audit_Untested_20261007，wheel SHA256 642d80f19aff9611196ca7e1bd7a2f212632f4bee887b6a3770f0b8a25608d0d，55包文件字节匹配，仅语法/Schema/构建/字节核对，功能/SDK/原生测试0。12/46/3及full_live_gate_passed=false不变，E盘旧源码未合入。最新DeepSeek增补 C:/Users/Public/Documents/MCP_HCL_DeepSeek_Security_Audit_Handoff_20261007_642d80f1.md，旧候选/回执与账号条件清理边界保留。

## 2026-10-07：NetStream导出事务软件更新，55声明

独立nat-transactions工作区新增hcl_apply_netstream，本地名字与VM绑定、共享全局设置保护、目的地址精确移除及保存/恢复稿见该工作区 docs/netstream-transactions-20261007.md。原生命名Exporter/monitor与流量等价仍缺，不提升完整复现结论。

候选 C:/Users/Public/Documents/MCP_HCL_NetStream_Untested_20261007，wheel SHA256 3714fc784b95efd1fad1a05d3e9bfa6e39b0a46992132b0bb6c396d21f0e8328，56包文件字节匹配。预计55工具/6资源，只有语法/Schema/构建/字节核对，功能/SDK/原生/流量测试0。E盘旧源码未合入，12/46/3及full_live_gate_passed=false不变。DeepSeek最新增补 C:/Users/Public/Documents/MCP_HCL_DeepSeek_NetStream_Handoff_20261007_3714fc78.md；旧候选/回执及账号条件清理边界保留。
