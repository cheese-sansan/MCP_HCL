# 控制平面实现与交接（dsh 分支）

> 面向在**另一个分支**上继续工作的 codex。
> 目标：读完本文你应当能（a）理解为什么控制平面这样做，（b）知道每一处代码在哪、契约是什么，（c）知道哪些是已验证的、哪些是推断的，（d）知道下一步做什么以及怎么验收。
>
> 相关文档：[路线图](roadmap.md)（目标与差距）、[后端协议观察记录](hcl-backend-protocol.md)（协议细节）、[ADR-0001](adr/0001-live-control-transport.md)（决策）。
> 分支：`dsh`。本文描述的实现**只存在于 dsh 分支**；其他分支没有这些文件。

---

## 0. 三分钟版本

1. HCL 自带一个面向机器的后端（`SimwareWrapper`，TCP `127.0.0.1:16600`）。它**可以脱离 GUI 独立启动**，因此协议可以安全、可重复地验证。
2. 本分支把 `backend.py` 从"2 个只读命令"扩展成一个**带证据等级的动词注册表**，并新增 `console.py`（命名管道设备控制台）。
3. 暴露 4 个新 MCP 工具；**所有会改状态的动作默认全部关闭**，需要 `MCP_HCL_ALLOW_LIVE_WRITE=1`。
4. 已用真实后端验证：读回版本/内存、开启拓扑会话、在同一会话上下发 `start`、干净关闭。
5. 未验证：任何需要 guest 真正启动才能做到的事（CLI 内容、ping、配置下发）。`start` 命令能被接受，但本机 guest 仍因 Hypervisor/VBS 冲突无法启动，且**没有任何设备被创建**，所以控制台管道还不存在。

**如果只记一件事：拓扑上下文绑定在 TCP 连接上，不是全局的。** 一次性连接发 `start` 会得到 `228`；同一个连接先发 `create_topology` 再发 `start`，才会真正进入 `SimwareTopo startVM`。

---

## 1. 已验证的事实（每条都有回执）

回执目录：`work/feasibility/dsh-20261001/`。

### 1.1 后端可脱离 GUI 启动

```
Start-Process 'D:\HCL\SimwareWrapper.exe' -WorkingDirectory 'D:\HCL'
```

- 端口 16600 在 **0.7 秒**内进入监听；进程可正常终止，端口随即关闭。
- 回执：`p2-live-verification.json` 的 `port_before=false`、`port_open_after_start=true`、`port_after_stop=false`。

**为什么重要**：P2 的全部验证都不需要启动 HCL GUI、不需要 VirtualBox 里的 guest、不需要窗口自动化。这是把"实时能力"从"实时门槛"上解耦的关键。

### 1.2 原始帧格式（逐字节抓取）

`capture_frames.py` 直接读 socket，得到：

| 请求 | 原始应答字节 |
| --- | --- |
| `simwarewrapper version` | `b'111111111-101-1.0.0&6.0.14\r\n/end'` |
| `simware create_topology mcphcl2 <dir> v7_sw_vlan_basic 10001` | `b'222222222-100\r\n/end'` |
| `simware start 1 0`（新连接） | `b'333333333-228\r\n/end'` |
| `simware normal_close True` | `b'444444444-100\r\n/end'` |

**两个必须记住的形状规则：**

1. **回复没有参数时，`-payload` 整段被省略**，不是 `-None`。即 `<id>-<code>\r\n/end`。
   早期实现用 `([0-9]+)-([0-9]{3})-(.*)` 解析，因此 `create_topology` 一律失败并报 `Backend response has an unknown wire format`。已修复，并有针对性回归测试。
2. 客户端关闭连接后，Wrapper 会把"读到空请求"当成一次新请求，**再补发一个没人认领的帧**（`send_reply(done=1, errorCode=200, parameters=None)`）。
   所以解析器必须**按请求 ID 匹配**，而不是"读到 `/end` 就当答案"。

### 1.3 拓扑上下文是 per-connection（本次最重要的发现）

在**同一次实验**里，同一个 `start 1 0` 得到两个不同结果，Wrapper 自己的日志给出解释：

```
# 新连接，直接 start
handle_one_request None, command is 'do_simware_start'.
send_reply(done=1, errorCode=228, parameters=None)

# 同一连接，先 create_topology
handle_one_request None, command is 'do_simware_create_topology'.
SimwareTopo __init__, TopoName is mcphcl1, TopoPath is 'e:\mcp_hcl\work\...\v7_sw_vlan_basic', TopoUDPPort is 10000
SimwareWrapperRequestHandler v7_sw_vlan_basic send_reply(done=1, errorCode=100, parameters=None)
...
handle_one_request v7_sw_vlan_basic, command is 'do_simware_start'.
SimwareTopo startVM
send_reply(done=1, errorCode=219, parameters=None)
```

- 处理器名从 `None` 变成 `v7_sw_vlan_basic`（取自拓扑路径的目录名），说明**连接获得了拓扑身份**。
- `228` = 没有拓扑上下文；`219` = 有拓扑但 `startVM` 失败（本次因为拓扑里根本没有 device 1）。
- 因此：**任何拓扑域动作都必须复用打开拓扑的那条连接。** 这是 `BackendSession` 存在的唯一理由。

顺带确认了 `create_topology` 的参数语义（日志直接打印）：`<TopoName> <TopoPath> <项目名> <TopoUDPPort>`。

### 1.4 关闭是干净的

```
handle_one_request v7_sw_vlan_basic, command is 'do_simware_normal_close'.
SimwareTopo disconnect mcphcl1
SimwareTopo disconnect mcphcl1 delete vm success
SimwareTopo disconnect mcphcl1 delete file success
send_reply(done=1, errorCode=100, parameters=None)
```

并且 `vm_root_unchanged: true` —— 整个实验**没有在 `C:\Users\<用户>\HCL VMs\` 留下任何东西**（前后快照逐条相同）。

### 1.5 后端读回（真实，非历史值）

`hcl_bridge_status` 对着真实 Wrapper：`status=verified`、`backend_version=1.0.0&6.0.14`、`reported_system_memory_mb=14708`、`verified_scope=version_and_memory_protocol_readback`。

这**闭合了上一轮报告中的一条未验证项**（此前 Wrapper 没运行，只拿到 `unverified`）。

### 1.6 写开关确实默认关闭

同一个探针跑两遍，只差环境变量：

| 调用 | 关闭时 | 打开时 |
| --- | --- | --- |
| `hcl_backend_topology(open…)` | `rejected / writes_disabled` | `accepted / response_code=100 / session_open=true` |
| `hcl_device_power(1)` | `rejected / writes_disabled` | 进入会话 → `response_code=219` |
| `hcl_console_exec(…)` | `rejected / writes_disabled` | `unverified / console_unavailable (FileNotFoundError)` |

注意最后一行：**打开开关也不会假装成功**。没有设备 → 没有管道 → 如实报 `unverified`。

---

## 2. errorCode 表（观测所得，非厂商文档）

| 码 | 观测到的含义 | 证据 |
| --- | --- | --- |
| `100` | 成功，无参数 | `create_topology`、`normal_close` |
| `101` | 成功，带参数 | `version`、`system_memory` |
| `200` | 通用错误 / 空请求补发帧 | 客户端关闭后的补发帧；无拓扑时的不识别命令 |
| `204` | 失败 | 历史日志（`delete_udp` 时 VirtualBox COM RPC 不可用） |
| `210` | 失败 | 历史日志 |
| `219` | `startVM` 失败 | 本次：拓扑存在但设备不存在 |
| `228` | 没有拓扑上下文 | 本次：新连接直接 `start` |

`_SUCCESS_CODES = {100, 101}`；其余一律按失败上报（**返回给调用方，不抛异常**），因为调用方需要看到码值。

---

## 3. 代码地图

### 3.1 `src/mcp_hcl/backend.py` —— 协议层

| 符号 | 职责 | 要点 |
| --- | --- | --- |
| `OBSERVED_VERBS` | 动词注册表 | 每个动词带 `service/kind/evidence/writes/invocable/build/note`。**这是唯一的白名单**，没有透传入口。 |
| `VerbSpec.describe()` | 供 `hcl_backend_capabilities` 输出 | `enabled = invocable and (writes_enabled or not writes)` |
| `_token/_name/_integer/_bool/_absolute_directory` | 参数整形 | 拒绝空白与控制字符 → **防协议行注入**（协议是空格分隔、换行结尾的） |
| `_frames(payload)` | 帧解析 | 只接受**已由 `/end` 终结**的帧；丢弃末尾不完整块；payload 段可选 |
| `_Wire` | 一条 TCP 连接上的收发 | **按请求 ID 匹配**帧；容忍补发帧；`extra_frames` 记录额外帧数 |
| `_invoke(exchange, verb, args, writes_enabled=…)` | 动词调用公共体 | 先查注册表 → 再查是否 invocable → 再查写开关 → 再整形参数 → 再发 |
| `BackendSession` | 持久连接 | `open_topology()` 成功后记住 `topology`；`invoke()` 复用同一连接 |
| `HclBackend._request` | **原有窄路径，未改动语义** | 只允许 `simwarewrapper version` / `system_memory`，其它一律 `ValueError` |
| `HclBackend.invoke` | 一次性连接调用 | 只适合不需要拓扑上下文的动词 |
| `HclBackend.connect()` | 打开持久会话 | 返回 `BackendSession` |
| `HclBackend.status()` | `hcl_bridge_status` 的实现 | 行为、字段、`verified_scope` 均未改变 |

**动词清单（16 项）：**

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

**为什么 `create` 不可调用**：它有 14 个位置参数，其中 6 个语义未知。猜错内存/槽位/标志可能创建出坏掉的虚拟机，而且 `delete` 的参数形状也没采全，坏掉的东西**删不掉**。宁可拒绝，也不要留下删不掉的垃圾。要启用它，先按 §7 的方法把字段补齐。

### 3.2 `src/mcp_hcl/console.py` —— 设备控制台

| 符号 | 职责 |
| --- | --- |
| `PIPE_PATTERN` / `describe()` / `endpoint()` | 只接受 `\\.\pipe\<topology>-device<N>`；**无法指向任意宿主管道** |
| `open_console_pipe()` | `os.open(..., O_RDWR|O_BINARY)` + `os.set_blocking(fd, False)`，带重试截止 |
| `ConsoleSession` | 非阻塞轮询读写：`drain()` 丢弃命令前到达的陈旧输出；`read_until_idle()` 收齐到静默 |
| `HclConsole.run()` | 门控 → 打开 → 结算并丢弃陈旧字节 → 发送 → 读取 → 组装证据 |

**关键实现决定：不用读线程，用非阻塞轮询。**
第一版用后台读线程，`close()` 时线程阻塞在 `read()` 上无法唤醒，测试直接挂死。已实测（`probe_nonblocking.py`）Windows 11 + Python 3.12 下 `os.set_blocking` 对**匿名管道和命名管道都可用**，于是改成轮询，彻底消除死锁。

控制台结论字段刻意分开，避免任何越级声明：
`verified_scope="console_channel_text_readback_only"`，并且 `guest_boot_verified`、`configuration_verified`、`connectivity_verified`、`full_live_gate_passed` **全部为 false**。

### 3.3 `src/mcp_hcl/server.py` —— MCP 面

新增会话状态（`create_server` 内闭包）：

```python
session_lock = threading.Lock()
session_state = {"session": None, "topology": None, "project": None, "commands": []}
```

**同一时刻只允许一个后端会话**，因为拓扑绑在连接上；第二个 `open` 会被 `session_already_open` 拒绝。

### 3.4 `src/mcp_hcl/parity.py`

`REGISTERED_TOOLS` 增加了 4 个名字，并附注释说明它们**不是上游等价声明**。61 项映射里**没有任何一行因此变成 implemented**。

---

## 4. MCP 工具契约

### 4.1 `hcl_backend_capabilities`

- 输入：无。**离线**，不开 socket。
- 输出关键字段：`status="verified"`、`verified_scope="observed_verb_registry_only"`、`endpoint`、`write_verbs_enabled`、`console_exec_enabled`、`topology_session_open`、`invocable_count`、`verbs[]`、`limitations[]`。
- 用途：让客户端先看清"哪些动词存在、哪些被拒绝、写开关开没开"。

### 4.2 `hcl_backend_topology`

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `action` | 是 | `open` / `close` / `status` |
| `topology` | `open` 必填 | `[A-Za-z][A-Za-z0-9_-]{0,31}`；会成为 `HCL VMs\<topology>\` 与管道名前缀 |
| `working_directory` | `open` 必填 | 绝对路径，**必须在配置的工程根内**，且不能含空白 |
| `project_name` | 否 | 默认取目录名 |
| `udp_port` | 否 | 默认 10000 |

结果：`accepted`（`response_code=100`，`verified_scope="backend_accepted_the_command_only"`，`session_open=true`）或带 `errors[].code` 的拒绝。

错误码：`writes_disabled`、`session_already_open`、`no_open_session`、`missing_argument`、`unknown_action`、`invalid_argument`、`outside_configured_roots`、`backend_unreachable`、`backend_error_code`。

> `action="status"` 是只读的，**不受写开关限制**。

### 4.3 `hcl_device_power(device: int, on: bool = True)`

- `on=False` → `unsupported`（**日志里没有任何停止动词**，不猜）。
- 写开关关闭 → `writes_disabled`（**先于**会话检查，保证"关着就是关着"）。
- 没有打开的会话 → `no_open_session`，并提示先 `hcl_backend_topology open`。
- 有会话 → 在同一连接上发 `simware start <device> 0`。
- 结果里带 `topology`，成功时 `verified_scope="backend_accepted_the_command_only"`。
- **语义边界**：`accepted` 只表示后端接受了命令。本次实测即便在正确会话上也是 `219`（拓扑里没有那台设备）。**不要**把它当"设备已启动"。

### 4.4 `hcl_console_exec`

| 参数 | 说明 |
| --- | --- |
| `command` | 单行；拒绝 CR/LF/NUL，长度 ≤512 |
| `pipe` | 可选；**必须**匹配 `\\.\pipe\<topo>-device<N>` |
| `topology` + `device` | 可选；与 `pipe` 二选一，服务端自行拼管道名 |
| `expect` | 可选；输出中必须出现的标记 |

结果：`output_received` / `no_output` / `unverified`（`console_unavailable`）/ `rejected`（`writes_disabled`、`invalid_request`）。
带 `discarded_stale_bytes`、`output_sha256`、`request_sha256`、`expect_found`。若 `expect` 未命中 → `errors=[{code:"expected_text_missing"}]`。

---

## 5. 开关与环境变量

| 变量 | 作用 |
| --- | --- |
| `MCP_HCL_ALLOW_LIVE_WRITE` | **总开关**。认 `1/true/yes/on`（大小写不敏感）。关闭时所有改状态的动作一律 `writes_disabled`。 |
| `MCP_HCL_BACKEND_PORT` | 默认 16600 |
| `MCP_HCL_PROJECT_ROOTS` | 分号分隔；`working_directory` 必须落在其中之一 |
| `MCP_HCL_OUTPUT_ROOT` | 阶段输出根 |
| `MCP_HCL_INSTALL_ROOT` | 默认 `D:\HCL` |

**建议的验证配置**（不写状态）：

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

要真的下发状态，再加 `"MCP_HCL_ALLOW_LIVE_WRITE": "1"`；**先确认 `working_directory` 指向隔离副本**。

---

## 6. 测试与复现

```powershell
# 全量（66 项，1 项因账号无 symlink 权限 skip）
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests

# 控制平面专项
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 -m unittest tests.test_backend_verbs tests.test_console -v
```

| 测试文件 | 覆盖 |
| --- | --- |
| `tests/test_backend.py` | 原有 4 项：真实 socket 往返、请求 ID 不符被拒、内存非法不被版本掩盖、非环回/变更命令被拒。**语义未改**。 |
| `tests/test_backend_verbs.py`（新） | 注册表与证据等级；写门控；不可调用动词；**参数不能破坏行格式**；逐条断言渲染出的命令行与观测形状一致；错误码不抛异常；不可达记 `unverified`；**帧解析三条规则**（未终结丢弃 / 无 payload 段 / 补发帧容忍）；**per-connection 拓扑规则**（一次性连接 228，会话内 100） |
| `tests/test_console.py`（新） | 管道名白名单；写门控；危险命令拒绝；陈旧输出被丢弃且不会混进本次回答；空读超时语义；**真实命名管道往返**（`CreateNamedPipeW` + `ctypes`，非 mock） |
| `tests/test_mcp_contract.py` | 契约层：发现面、61/5 清单、计划校验矩阵、路径安全、命名语法、参数边界，以及**控制平面工具必须门控且不宣称实时成功** |

真实后端验证（会自行启动并停止 Wrapper，不动 GUI、不动 guest）：

```powershell
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 E:\MCP_HCL\work\feasibility\dsh-20261001\p2_live_probe.py
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 E:\MCP_HCL\work\feasibility\dsh-20261001\capture_frames.py
```

---

## 7. 回执索引（断言 → 证据）

| 断言 | 证据文件 |
| --- | --- |
| Wrapper 可独立启动、端口起落 | `p2-live-verification.json` |
| 每种动词的原始字节 | `capture_frames.py` 的控制台输出 |
| per-connection 拓扑（228 vs 219） | `p2-live-verification.json` 的 `wrapper_log_tail` |
| 未留下虚拟机 | `p2-live-verification.json` 的 `vm_root_unchanged=true` |
| 写开关默认关闭 | `p2-live-verification.json` 的 `gate_off` 段 |
| 命名管道可用 | `console-test-run2.txt`、`probe_nonblocking.py` |
| 66 项测试 | 提交前最后一次 `unittest discover` 输出 |
| P4 被权限阻断 | `work/feasibility/lab_boot_20261001/elevation-blocked-20261001.json` |

---

## 8. 未验证 / 已知缺口 / 危险区

**未验证**

- `start` 在**同时存在真实设备**时能否真正拉起 guest。本机 guest 受 Hypervisor/VBS 冲突阻塞（`VERR_NEM_VM_CREATE_FAILED`），且本次拓扑里没有设备，只能证明"命令进入了 `SimwareTopo startVM`"。
- 控制台**实际输出**。管道只有在设备控制台被创建后才存在；本次 `FileNotFoundError` 是正确结果，不是缺陷。
- 命名管道的并发语义：HCL 的 PuTTY 已连接时能否第二客户端接入、是否互斥、是否为原始终端字节流 —— **全部未测**。CLI 方案成立与否取决于这一项。
- `create` / `delete` / `create_udp` 的字段语义。
- `set_hcl_tcp 18600` 打开的那个端口究竟是什么第二通道。

**危险区（改代码前务必看）**

1. **不要在一次性连接上拓扑域动词**。会得到 `228`，而且很容易被误读成"设备不存在"。
2. **不要放宽 `_frames` 的终结符要求**。放宽会让 TCP 分片悄悄截断数值（已发生过）。
3. **不要假设回复一定带 payload 段**。
4. **不要开 `create`**，除非你先把字段补齐并且能删干净。
5. **后端直接改拓扑不会刷新 GUI 画布**（README 已记录）。所以拓扑变更仍应走 relay：写 `.net` → 让 HCL 载入。
6. 真实 Wrapper 会**写虚拟机目录**。开写开关前先确认 `topology` 名与 `working_directory` 是隔离副本，并保留前后快照。

---

## 9. 下一步（按优先级，含验收）

### 9.1 校准 `create_udp`（解锁控制台）
在隔离副本上让 HCL **自己**加载工程一次，从日志抓 `create_udp` 的完整请求行与返回码；或者用一次受控实验直接测量 UDP 端口分配规律。
**验收**：能在不起设备的情况下预测管道名，且 `create_udp` 的 7 个参数全部有依据。

### 9.2 补齐 `create` / `delete`（解锁设备生命周期）
同法，从 HCL 打开工程时的日志抓完整 `create` 行（含端口表与镜像名），并抓一次 `delete`。
**验收**：在隔离拓扑上创建再删除一台设备，`vm_root` 前后一致。

### 9.3 命名管道并发测量（决定 CLI 方案可行性）
在 HCL 的 PuTTY 已连接同一管道时，尝试第二客户端打开；测只读与读写两种情况。
**验收**：给出"可并发 / 需互斥 / 不可共享"的明确结论与原始回执。**结论为"不可共享"时，CLI 方案必须回到评审**，改用 HCL 自己的控制台或 `SimwareMultiCC`。

### 9.4 把会话状态接进 P3 relay
`hcl_backend_topology` 目前只能打开后端拓扑，GUI 不知道。下一步应验证：后端建立拓扑后，GUI 是否存在重新读取后端拓扑的动作。若有，D1 的增量编辑可以完全绕开窗口自动化。
**验收**：给出"GUI 是否重读"的确定结论。

### 9.5 P4（需要用户提权，见 §10）

---

## 10. P4 状态：启动项**已创建并回读验证**，剩下的是使用者重启

### 10.1 已完成的动作（2026-10-01）

使用者启用 Windows 11 内置 `sudo` 并作为设备所有者授权后执行：

```powershell
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Create `
  -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
```

> 本机 sudo 处于**强制新建窗口模式**（`sudo config` 如此报告），因此 `--inline` 会被拒绝，提权进程的 stdout 不回到调用终端。**凡是提权动作都要用"写文件回执"的方式取结果**，不要依赖管道输出。

回执：`work/feasibility/lab_boot_20261001/2704c0bffb434eeaaaabbbebed6c379c/result.json`，`status = "verified"`，`verified_scope = "lab_boot_entry_created_and_read_back_only"`。

| 项 | 值 |
| --- | --- |
| 新启动项 GUID | `{1031110f-89bd-11f0-ad29-c0bfbeee1ce7}` |
| 描述 | `MCP_HCL Lab (Hypervisor and VSM off)` |
| 回读 | `hypervisorlaunchtype Off`、`vsmlaunchtype Off` |
| BCD 备份 | `...\2704c0bf...\bcd-before.bak`，SHA256 `2D849DC815CF3A5551EDF4B3B09DFA1539FEAE0384250B528CA93DE68305FB4A` |
| `{current}` | **未变**，仍为 `Windows 11` / `hypervisorlaunchtype Auto` |
| `{bootmgr}` default | **未变**，仍为 `{current}` |
| `displayorder` | 新项**追加在最后** |
| `reboot_performed` | `false`（脚本不重启） |

提权本身也单独验证过（`probe-elevation.ps1`）：`elevated=true`、`can_read_bcd=true`。

> **备份是机器本地的。** `bcd-before.bak` 位于 `work/` 下，而 `work/` 被 Git 忽略，因此不会随仓库传播，清理 `work/` 会丢失它。它只用于灾难恢复；日常回退用 `-Action Remove`（见 §10.3）即可，不需要该文件。若要长期保留，请自行复制到 `work/` 之外。

### 10.2 使用者需要做的唯一动作

**手动重启，在启动菜单选择 `MCP_HCL Lab (Hypervisor and VSM off)`。**

该会话的 Hypervisor/VBS 防护与依赖功能不可用——这是一次性的显式选择，不是静默关闭全局安全功能；日常启动项未受影响。

重启后运行（只读，不改任何设置）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_environment.ps1 `
  -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
```

它会判定三件事并给出 `verdict`：是否真的启动进了实验项（`bcdedit {current}` 是否显示该描述且 `hypervisorlaunchtype Off`）、本会话是否仍有 Hypervisor、VirtualBox 是否可读。`verdict=lab_entry_active_and_no_hypervisor` 时才继续跑剩余电源门槛。

### 10.3 回退

```powershell
sudo run powershell -NoProfile -ExecutionPolicy Bypass `
  -File E:\MCP_HCL\scripts\hcl_lab_boot.ps1 -Action Remove `
  -EntryId '{1031110f-89bd-11f0-ad29-c0bfbeee1ce7}' `
  -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001
```

脚本的删除保护会拒绝删除"当前正在运行的项"或"已被设为默认的项"，因此**必须先在普通 Windows 项下运行**。

### 10.4 仍未完成

- 重启本身（使用者操作）。
- 启动一台隔离设备并读到 Comware 提示符——这是 P4 的真正验收，也是 P5（24 项 CLI 家族）的前置。
- 修复效果的**因果确认**：目前只能说"启动项已按要求设置且回读正确"，不能说"guest 现在一定能起来"。

---

## 11. 给 codex 的操作清单

```powershell
# 1. 确认你在自己的分支上，dsh 的提交已经能看到
git log --oneline -5

# 2. 跑全量测试，确认基线是绿的
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests

# 3. 只读地把控制面看清楚（不会写任何东西）
#    用 MCP 客户端调用：hcl_backend_capabilities、hcl_bridge_status

# 4. 要动真实后端时，先启动 Wrapper（不需要 GUI）
Start-Process 'D:\HCL\SimwareWrapper.exe' -WorkingDirectory 'D:\HCL'
#    验证完务必 Stop-Process；结束时确认 VBoxSVC 也退出了

# 5. 真实后端验证脚本（自己起停 Wrapper）
E:\MCP_HCL\.venv\Scripts\python.exe -X utf8 E:\MCP_HCL\work\feasibility\dsh-20261001\p2_live_probe.py
```

**改动纪律（本分支已建立，请延续）**

- 每个新动词都必须标注 `evidence`（`verified`/`observed`/`inferred`）与是否 `writes`。
- 写动词默认 `invocable=False`，除非字段语义有据可依。
- 每个"成功"都要有 `verified_scope`，并且**不得跨层推断**：命令被接受 ≠ guest 启动 ≠ 配置下发 ≠ 网络连通。
- 任何对外部世界的成功声明都要附回执路径，回执进 `work/`（该目录被 Git 忽略）。
