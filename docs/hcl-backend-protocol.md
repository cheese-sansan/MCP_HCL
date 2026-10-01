# HCL 后端协议观察记录（SimwareWrapper）

> **证据等级：观察所得（OBSERVED），不是厂商文档。**
> 本文内容全部来自本机 HCL 5.10.3 安装自带的运行日志与配置文件的**只读**检查，没有反编译、没有修改任何厂商文件、没有复制厂商程序或镜像进仓库。
> 所有条目都带状态标签：**OBSERVED**（在日志中出现过）、**IMPLEMENTED**（仓库代码已使用）、**VERIFIED**（有回执证明）。**未经实测的字段含义一律标注"推断"。**

> **2026-10-01 更新（dsh 分支实测）**：下文 §2/§3/§4 的一部分已被**真实后端**验证，并发现两条此前不知道的帧规则。实现级细节与逐条回执见 [控制平面实现与交接](control-plane.md)。要点：
> 1. `SimwareWrapper.exe` **可脱离 GUI 独立启动**（0.7 秒内监听 16600），因此协议可安全复现验证。
> 2. 回复**没有参数时省略整段 payload**：原始字节 `b'222222222-100\r\n/end'`，不是 `-None`。
> 3. 客户端断开后 Wrapper 会**补发一个无人认领的帧**（`errorCode=200`），解析必须按请求 ID 匹配。
> 4. **拓扑上下文绑定在 TCP 连接上**：新连接直接 `start` → `228`；同一连接先 `create_topology` 再 `start` → 进入 `SimwareTopo startVM`。
> 5. 新增观测错误码 `219`（`startVM` 失败）。
> 6. `create_topology` 参数语义经日志确认：`<TopoName> <TopoPath> <项目名> <TopoUDPPort>`。

---

## 1. 为什么这份文档重要

项目此前把"实时控制"等同于 Qt 窗口自动化，因此成本高、失败模式多。实际上 HCL 有一个**面向机器的行式请求/应答协议**，HCL 自己就通过它完成：建拓扑、建设备、分配控制台管道、开关虚拟机。当前仓库只用了其中 2 个只读命令。

掌握这个协议后，"控制平面"可以绕开窗口自动化，只保留一个窗口动作（让 HCL 载入工程）。

---

## 2. 传输与帧格式

| 项 | 值 | 状态 |
| --- | --- | --- |
| 端点 | TCP `127.0.0.1:16600`（`[vbox 127.0.0.1:16600]` 出现在每个 `.net` 的头部块） | IMPLEMENTED + VERIFIED |
| 请求 | `<id> <service> <verb> [args...]\n`，`id` 为十进制数字，`service` 为 `simwarewrapper` 或 `simware` | IMPLEMENTED（`backend.py`） |
| 应答 | `<id>-<code>-<payload>\r\n/end` | IMPLEMENTED + VERIFIED |
| 关联 | 应答中的 `<id>` 必须等于请求 `<id>`，否则视为无效 | IMPLEMENTED + VERIFIED |
| 成功码 | `100`、`101`（日志中 `100` ×240、`101` ×75） | OBSERVED |
| 失败码 | `200`（×6）、`204`（×1）、`210`（×1）、`228`（×1） | OBSERVED |

`backend.py` 目前只接受 `{100, 101}`，且只放行两个命令。

---

## 3. 已观察到的命令

`service = simwarewrapper`：

| 命令 | 参数 | 状态 |
| --- | --- | --- |
| `simwarewrapper version` | 无 → `1.0.0&6.0.14` | IMPLEMENTED + VERIFIED |
| `simwarewrapper system_memory` | 无 → `14708`（MB） | IMPLEMENTED + VERIFIED |

`service = simware`（全部为 OBSERVED，仓库未使用）：

| 命令 | 观察到的参数形状 | 日志出现次数 | 备注 |
| --- | --- | --- | --- |
| `create_topology` | `<topo> <workingdir> <项目名> <udp端口>`，例：`topo1  e:\...\v7_sw_vlan_basic  v7_sw_vlan_basic  10000` | 13 | 让后端为某个工程目录建立拓扑上下文 |
| `create` | `<名称> <序号> <0> <内存> <384> <600> "{端口表}" <udp端口> <MAC> <镜像vmdk> <1> <0>` | 44 | 端口表见 §5 |
| `create_udp` | `<设备号> <0> <1> <udp端口> <127.0.0.1> <端口2> <1>` | 68 | **应答返回控制台管道名**，见 §4 |
| `delete_udp` | `<设备号> <0> <0>` | 51 | |
| `delete` | `<名称|设备号> ...` | 29 | 参数未完整采样 |
| `start` | `<设备号> <0>`，例：`start 6 0` | 1 | **电源开**；这一次正是历史上启动失败的那次 |
| `start_recover` | 无 | 7 | 批量/恢复启动 |
| `set_memory` | 未采样 | 2 | |
| `set_version_path` | 未采样 | 21 | |
| `save` | 未采样 | 4 | |
| `set_hcl_tcp` | `<端口>`，例：`18600` | 12 | HCL 侧另开一个 TCP 端口 |
| `set_hcl_normal_close` | `<True|False>` | 17 | 生命周期 |
| `normal_close` | `<True|False>` | 17 | 生命周期 |

> 字段含义中除 `create_topology`（可直接对齐）外均为**推断**：本文只保证"参数顺序与数量与日志一致"，不保证每个字段的语义。实现时必须先做只读/无副作用验证。

**可靠性提示**：`start` 只被观察过 1 次，而且结果失败。因此"`start` 是开电源的正确命令"属于**强推断，未验证**。

---

## 4. 控制台通道：命名管道

这是最有价值的发现。

`create_udp` 的应答直接给出该设备的控制台管道名：

```
INFO: SimwareWrapperRequestHandler v7_sw_vlan_basic send_reply(
        done=1, errorCode=101, parameters=('\\\\.\\pipe\\topo1-device6', False))
```

- 命名规则：`\\.\pipe\<拓扑名>-device<设备号>`（观察到 `topo1`、`topo77`）。
- HCL 自己的控制台是用 **PuTTY 串口模式**打开这个管道的：
  `D:\HCL\sessions\default_conf` 中 `Protocol\serial`、`PortNumber\115200`、`SerialSpeed\9600`。
- 结论：**CLI 通道的接入点是明确的**——同一个管道可以被自己的进程以文件方式打开并读写，不需要模拟键盘输入。

**未验证的部分**：该管道允许几个并发客户端、HCL 的 PuTTY 占用时是否互斥、读写是否为原始终端字节流。这些必须在实现前用只读方式测清楚。

---

## 5. 离线可推导的型号端口表

`create` 请求里带着该型号完整的场景端口表，例如 S5820V2-54QS-GE：

```
{0:(1,'M-GE_0/0'), 1:(3,'GE_0/1'), 2:(3,'GE_0/2'), ... ,
 49:(4,'XGE_0/49'), 50:(4,'XGE_0/50'), 51:(4,'XGE_0/51'), 52:(4,'XGE_0/52'),
 53:(5,'FGE_0/53'), 54:(5,'FGE_0/54')}
```

元组第二项是端口类型 ID，而 `D:\HCL\deviceInfo.ini` 的 `[PHY_PORT_VALUE]` 给出了同一套编号：

```
PHY_ETH_GE = 3      PHY_ETH_XGE = 4     PHY_ETH_FGE = 5
```

**这意味着"型号 → 场景端口"的映射可以在完全不启动 HCL 的情况下推导出来**，只要把 `deviceInfo.ini` 的端口族定义与各型号的 `devicecfgs` 接口列表做连接即可——这正是交接文档列为缺失的"补全型号端口映射"。当前 `hcl://catalog/ports` 只返回了端口族定义，尚未做这一步连接。

---

## 6. 虚拟机与工程布局（OBSERVED）

- 每台设备一个 VirtualBox 虚拟机，由基础模板克隆：`GetVMByName, strName=Simware_Base` → `SimwareVM clone`。
- 目录布局：`C:\Users\<用户>\HCL VMs\<拓扑名>\device<设备号>\<拓扑名>-device<设备号>.vbox`。
- 配置盘指向工程目录下的 `ConfigDisk\device<N>.vdi`（基于阶段副本时会指向副本）。
- 拓扑键来自 `.net` 所在目录的父级名（`HCL VMs\topo1\...` ↔ `.net` 的 `[vbox ...]` 上下文），设备号来自 `device_id`。

这些与仓库中已记录的 `\\.\pipe\topo1-device6`、`HCL VMs\topo1\device6` 完全一致。

---

## 7. 与仓库现状的落差

| 能力 | 后端已具备 | 仓库已实现 |
| --- | --- | --- |
| 版本 / 内存回读 | ✅ | ✅ |
| 建立拓扑上下文（指定工程目录） | ✅ | ❌ |
| 建设备 / 删设备 | ✅ | ❌ |
| 取控制台管道名 | ✅ | ❌ |
| 电源开 | 强推断 | ❌ |
| 生命周期与保存 | ✅ | ❌ |

---

## 8. 实现时必须遵守的约束

1. **白名单，不做透传。** 只接受本文件第 3 节列出的动词，参数做结构校验；不提供"任意后端命令"入口。
2. **写动词默认关闭。** `create`/`delete`/`start`/`save` 等造成状态变化的命令必须显式开启，并落回执。
3. **请求关联。** 每次请求带 `operation_id`/`request_id`，应答 ID 不匹配即丢弃；超时与 65536 字节上限沿用现有实现。
4. **不做任意宿主管道。** 控制台客户端只接受由 `create_udp` 应答返回、且属于当前工程与设备号的管道名。
5. **单一真值来源。** 后端直接改拓扑不会刷新 GUI 画布（README 已记录）。所有拓扑变更应经 relay 架构由 HCL 载入工程来完成；后端写入仅用于 HCL 没有等价动作的场景。
6. **不夸大。** 命令被接受 ≠ guest 启动成功 ≠ 配置下发成功 ≠ 网络连通。三类结论必须分别取证。
7. **版本绑定。** 本文件只对 HCL 5.10.3 + VirtualBox 6.0.14 声明有效；换版本需重新观察。

---

## 9. 如何继续采集（可重复的方法）

HCL 把每一次请求和应答都写进自己的日志，因此**不需要抓包或反编译**即可扩展这份清单：

- 日志位置：
  - `D:\HCL\Log\SimwareWrapperLog\<用户>-SimwareWrapper.log`（后端请求/应答）
  - `D:\HCL\Log\HCLLog\HCL.log`（GUI 侧，含 `NETFile`、`Core.Dynagen.simware_lib` 的拓扑读写）
  - `D:\HCL\Log\SimwareMultiCCLog\SimwareMultiCC.log`（多控制台客户端）
- 方法：在 HCL 里做一个动作 → 读日志 → 找到 `handle_one_request ... command is 'do_simware_<verb>'` 与紧随的 `send_reply(done=..., errorCode=..., parameters=...)`。
- 日志会包含使用者路径与工程名，属个人数据，**不要整段复制进仓库**；本文只保留协议形状。

首次采集建议（只读、可回退）：在隔离副本上开关一次设备、建立/删除一条链路，观察 `start`、`delete`、`create_udp` 的完整请求行与返回码，用来确认 §3 的推断字段。
