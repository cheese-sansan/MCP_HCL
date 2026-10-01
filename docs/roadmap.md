# MCP_HCL 路线图：从 11 个工具到上游 61 项等价

更新：2026-10-01（分支 `dsh`）。本文是持久性的目标—差距—方案文档，取代临时交接文档里的"后续推进顺序"一节。

配套文档：[HCL 后端协议观察记录](hcl-backend-protocol.md)、[ADR-0001 实时控制通道](adr/0001-live-control-transport.md)、[上游功能对照表](upstream-parity.md)、[实时门槛](live-gate.md)。

---

## 0. 结论摘要

项目卡住的原因不是"实时门槛没通过"，而是**把整个目标耦合到了最脆弱的那个控制通道上**。三个事实改变了判断：

1. HCL 自带一个可观测的**后端控制平面**（`SimwareWrapper`，TCP `127.0.0.1:16600`）。它自己的运行日志完整记录了协议动词、参数形状、返回码，以及**控制台管道的分配方式**（详见 [后端协议](hcl-backend-protocol.md)）。当前代码只用了其中 2 个只读查询，其余 13 个已观察到的动词一个都没用。
2. 61 项里有 **14 项完全不依赖任何实时能力**（规划 5、目录 5、生成 4），其中只有 3 项已实现。这 11 项 + 3 个资源**今天就能做**，却被"实时门槛未过"整体阻塞。
3. 上游自身是 `domain（纯计算）/ generator（纯生成）/ executor（实时执行）` 三层；本仓库目前只有 `file + plan` 两层，缺的首先是**纯计算层**，而不是实时层。

因此建议的解法是**换控制平面 + 解开依赖耦合**，而不是继续打磨 Qt 窗口的像素级自动化。

---

## 1. 先定义"等价"

"复现上游"必须拆成三种强度，并分别声明，否则永远无法判断完成度：

| 级别 | 含义 | 判据 |
| --- | --- | --- |
| **L1 接口等价** | 同名工具存在，参数能表达同一意图 | 客户端 `tools/list` 可见、schema 可表达 |
| **L2 效果等价** | 在 HCL 上产生与 Packet Tracer 相同的可观察效果 | 工程文件 / 画布 / 设备状态的可观察变化 |
| **L3 证据等价** | 有与请求绑定的回读证据，失败可归因 | `operation_id` + 回读 + 回执 |

当前只有 4 项达到 L1+L3 的窄范围（`list_devices`/`get_device_details`/`list_projects`/`bridge_status`，且 `verified_scope` 都限定在安装资料或后端协议回读）。**其余 57 项尚未达到任何一级。**

目标应表述为：每一项要么达到 L1+L2+L3，要么给出"明确不支持/无原生等价"的结论并留下依据。

---

## 2. 现状快照（均来自本轮实测回执）

| 项 | 实测值 | 回执 |
| --- | --- | --- |
| 注册面 | 11 工具 / 3 资源，版本 0.1.1，`protocolVersion=2025-11-25` | `work/feasibility/single-modal-20261001/receipt-20261001.json` |
| 上游映射 | 61 工具 4 implemented / 54 planned / 3 unverified；5 资源 2/3/0；`completion=incomplete` | 同上 A4 |
| 只读业务 | 目录、工程、计划、映射全部按声明工作 | 同上 A3–A12 |
| 阶段生成 | `stage_copy` 6/4 → `stage_add_device` 7/4 → `stage_link` 7/5，回读一致，源工程逐字节不变 | 同上 C1–C5 |
| 实时闭环 | 发现面中画布/电源/CLI/ping/抓包工具为 0 个 | 同上 D1 |
| 本地测试 | 38 项通过（22 原有 + 16 新增契约） | `work/feasibility/dsh-20261001/unittest-full-dsh-final.txt` |
| guest 启动 | 历史失败 `VERR_NEM_VM_CREATE_FAILED`，未重跑 | `work/feasibility/environment_20261001/` |

---

## 3. 根因分析

### 3.1 错误耦合：一个硬阻塞被当成全局前置

本机确实有一个硬阻塞：VirtualBox 6.0.14 与 Windows 11 build 26200 的 Hypervisor/VBS 冲突（`VERR_NEM_VM_CREATE_FAILED`）。它阻塞的是**guest 启动**。但项目把它当成了"所有实时能力"的前置，进而当成"所有能力"的前置。实际上：

- 规划、目录、生成三层**完全不需要**它；
- 后端控制平面的拓扑/设备/控制台管道操作**也不需要**它（它们只操作 VirtualBox 的虚拟机定义，不需要 guest 跑起来）。

### 3.2 控制平面选错

已有的实时能力全部建立在 **Qt 窗口自动化**上：控件树遍历、`InvokePattern`、`WM_SETTEXT`、像素投影、菜单特征核对。这条路线的失败模式在文档里已经记满：中权限错误 5、锁屏 `LockApp`、画布平移导致固定像素命中注释、模态改变句柄、旧 PID 不可复用。它**能成功**（打开/保存副本、增删设备与链路都成功过），但它的成本随动作数线性增长，且每一步都要重新标定。

与此同时，HCL 有一个**面向机器的、行式请求/应答的后端协议**，HCL 自己就用它完成建拓扑、建设备、分配控制台管道、开关虚拟机。当前代码只用了 2 个只读命令。这是"绕开最脆弱层"的机会。

### 3.3 缺的是纯计算层，不是实时层

上游的导入结构显示它是三层：`domain/services/*`（validator、auto_fixer、explainer、estimator、orchestrator、topology_diff、security_audit、port_inspect、packet_trace）、`infrastructure/generator/*`（ptbuilder、cli_config、acl_cli）、`infrastructure/execution/*`（manual_executor、deploy_executor、live_bridge、file_bridge、bridge_token）。

本仓库已有 `file_bridge` 的等价物（阶段工程）和半个 validator，**没有** auto_fixer / explainer / estimator / diff / audit / 任何 generator。也就是说，11 项零依赖工具的缺失不是因为被阻塞，而是因为没人做。

### 3.4 契约层缺陷（本轮测试暴露）

| 编号 | 问题 | 影响 |
| --- | --- | --- |
| R1 | 未知参数被静默忽略，必填参数联动只在"部分提供"时报错 | `connect_to` 拼错 → 返回 `staged` 但没连线，静默半成品 |
| R2 | 损坏工程（`device_id = abc`、`x = not-a-number`）以工具错误逃逸，而非业务 `rejected` | 客户端无法只靠 `status` 判断结果 |
| R3 | `errors[]` 形状不一致：语义错误 `{code,message}`，结构错误是 pydantic 原始 `{type,loc,msg,url}` | 按 `code` 分支的客户端在结构错误上取不到键 |
| R4 | `operation_id` 每次调用新生成，不是可跨接口关联的稳定键 | 不满足"请求关联证据"要求 |
| R5 | 无幂等键；阶段名重复只能靠"目录已存在"拒绝 | 重试语义靠猜 |

---

## 4. 关键证据（决定方案的三条）

1. **后端协议可用且可观测。** 日志记录了 13 个动词的实际调用与参数，包括 `create_topology`、`create`、`create_udp`、`delete`、`delete_udp`、`start`、`start_recover`、`set_memory`、`set_version_path`、`save`、`normal_close` 等；返回码 `100/101` 为成功，`200/204/210/228` 为失败。详见 [hcl-backend-protocol.md](hcl-backend-protocol.md)。
2. **控制台是一个命名管道，并且由 `create_udp` 的应答把名字交出来**：`create_udp` → `('\\.\pipe\topo1-device6', False)`。HCL 自己的 PuTTY 会话配置是 `Protocol=serial`、`PortNumber=115200`，即**把该管道当串口打开**。这给出了 CLI 通道的确切接入点，不需要模拟键盘。
3. **HCL 打开 `.net` 时会自己下发完整后端调用。** README 已记录的实测：从阶段工程打开第 7 台路由器后，日志出现 `NETFile::create_node`、`NETFile::add_connection`，且双向 `create_udp` 都返回成功，第 7 台 VM 的配置盘指向阶段工程。**这意味着"让 HCL 自己把文件变成画布"这条链路已经验证过。**

同时必须承认一条限制：**后端直接建设备不会更新 GUI 画布**（README 已明确记录）。画布的真值在 HCL 进程内，`.net` 只是导出。

---

## 5. 把 61 项重新归类

按"需要什么才能做"重新分类，而不是按上游的功能域：

| 依赖类 | 数量 | 含义 | 已实现 |
| --- | --- | --- | --- |
| **D0 离线** | 14 | 不需要 HCL 进程，纯计算或本地文件 | 3 |
| **D1 后端控制平面** | 19 | 需要 SimwareWrapper + 让 HCL 载入工程，**不需要 guest 启动** | 1 |
| **D2 需要已启动 guest** | 24 | 需要控制台 CLI，因此需要 guest 真正启动 | 0 |
| **D3 无原生等价证据** | 3 | PT 专有的逐事件仿真语义 | 0 |
| **D4 需视觉验收** | 1 | 截图，单模态 Agent 无法验收 | 0 |

<details>
<summary>逐类清单</summary>

**D0（14，已实现 3）** — 规划：`estimate_plan`、`explain_plan`、`fix_plan`、`plan_topology`、`validate_plan`（部分）；目录：`list_devices` ✅、`get_device_details` ✅、`list_projects` ✅、`list_modules`、`list_templates`；生成：`export`、`generate_configs`、`generate_script`、`load_project`。资源：`catalog/aliases`、`catalog/cables`、`catalog/templates`。

**D1（19，已实现 1）** — 编辑：`add_device`、`add_link`、`add_module`、`delete_device`、`delete_link`、`install_modules_batch`、`move_device`、`rename_device`、`set_port`；画布：`add_note`、`clear_annotations`；会话：`bridge_status` ✅、`open_project`、`save_project`、`query_topology`、`export_topology`；备份工作区：`project_metadata`、`workspace_options`；检查：`device_power`。

**D2（24）** — 策略：`apply_acl`、`apply_acl_object`、`apply_nat`、`remove_acl`、`remove_acl_object`、`remove_nat`；网络配置：`apply_hardening`、`apply_interface_tuning`、`apply_port_security`、`apply_stp`、`apply_vlan`；遥测：`apply_netflow`、`read_qos`；验证：`diff`、`health_check`、`verify_connectivity`；检查：`audit_security`、`inspect_ports`、`read_vlans`；备份：`backup_config`；会话：`send_raw`、`live_deploy`；交付：`deploy`、`full_build`。

**D3（3）** — `read_packet_trace`、`simulation_mode`、`simulation_step`。

**D4（1）** — `screenshot`。

</details>

**这张表就是路线图的主轴：先做 D0，再打通 D1 的控制平面，最后才轮到需要超分修复的 D2。**

---

## 6. 分阶段路线

每个阶段都给出：范围、验收标准、依赖、需要的授权。

### P0 — 契约硬化（D0 前置，约 1 天）

把 §3.4 的 R1–R5 修掉。这些是**所有后续工具的地基**，而且现在改成本最低。

- R1：`stage_add_device` 的 `connect_to/connect_to_port/new_port` 改为"给一个就报错"；对未知参数名拒绝而不是忽略。
- R2：损坏工程一律返回业务 `rejected`（把 `summary()` 的 `int()/float()` 包进 `ProjectError`）。
- R3：结构错误也映射成 `{code: "invalid_plan_structure", message, detail}`。
- R4/R5：引入调用方可见的 `request_id` 回显与可选 `idempotency_key`；阶段名重复时按幂等键返回同一结果或明确冲突。
- 统一结果信封：`status / operation_id / request_id / target / verified_scope / evidence / errors[{code,message}] / warnings / runtime_verified / full_live_gate_passed`。

**验收**：`tests/test_mcp_contract.py` 的 16 项 + 新增的严格参数用例全绿；5 个旧接口保持兼容（不删字段，只增语义）。

### P1 — 离线层，把 11 项 + 3 个资源做完（最大收益，无外部依赖）

- **目录 2 项 + 3 资源**：`list_modules`、`list_templates`、`hcl://catalog/{aliases,cables,templates}`。数据源是本地 `devicecfgs`/`deviceInfo.ini`，无实时依赖。
- **规划 4 项 + 补全 validate_plan**：`plan_topology`（自然语言/结构化请求 → 计划）、`estimate_plan`（资源估算）、`explain_plan`（人类可读解释）、`fix_plan`（自动修复），以及 `validate_plan` 的服务参数校验（DHCP/VLAN/ACL/NAT/OSPF 等的字段级规则）。
- **生成 4 项**：`load_project`（工程 → 计划，是 `inspect_project` 的语义升级）、`export`（导出工程/计划/配置包）、`generate_configs`（Comware 文本生成，**只生成不下发**，显式标注 `runtime_verified=false`）、`generate_script`（可回放的命令序列）。

**验收**：`parity_report` 的 implemented 从 4 升到约 18；新增用例全部离线可回归；生成物用本机固件版本串标注，但**不声称任何命令被设备接受**。

**依赖**：无。**授权**：无。

### P2 — 控制平面（关键路径）

把 `backend.py` 从"2 个只读命令"扩成一个**受限的白名单适配层**：

- 只接受已观察到的动词白名单，参数做结构校验；不接受任意命令透传。
- 请求 ID 关联、超时、65536 字节上限（已有）。
- 控制台客户端：`create_udp` 取回 `\\.\pipe\<topo>-device<N>`，用命名管道做**请求关联的 CLI 会话**（绑定 工程/VM/请求、拒绝旧输出、不允许任意宿主管道、不抢占会话）。
- **写入动词默认关闭**，需要显式开启并留回执。

**验收**：`open_project`/`save_project`/`query_topology`/`export_topology`/`project_metadata`/`workspace_options` 达到 L2+L3；`device_power` 的**命令级**成功与失败都能回读归因。

**约束**：`start` 命令能否让 guest 真正启动，取决于 P4，与 P2 无关；P2 只保证"命令被 HCL 接受并可回读"。

**授权**：使用未公开的厂商内部协议属反向工程，建议由用户明确确认（见 [ADR-0001](adr/0001-live-control-transport.md)）。

> **进展（2026-10-01，已授权并完成第一层）** —— 详见 [控制平面实现与交接](control-plane.md)。
>
> 已完成：动词注册表（16 项，逐项标证据等级与写标记）、写总开关 `MCP_HCL_ALLOW_LIVE_WRITE`、帧解析（含两条实测规则）、**持久连接会话**（拓扑上下文绑在连接上）、命名管道控制台客户端（非阻塞、丢弃陈旧输出）、4 个新 MCP 工具、66 项测试。
>
> 已用真实后端验证：版本/内存读回、`create_topology` 被接受（`errorCode=100`）、同一会话内 `start` 进入 `SimwareTopo startVM`、`normal_close` 干净回收且**未留下任何虚拟机**、写开关关闭时三个工具全部 `writes_disabled`。
>
> 仍属 P2 未完成：`create`/`delete`/`create_udp` 的字段语义（当前**刻意不可调用**）、命名管道并发语义、GUI 是否重读后端拓扑。

### P3 — 画布与工程闭环（relay 架构）

不要试图用像素自动化实现"增量编辑当前画布"，而是把已验证的链路做成闭环：

```
阶段写盘(.net)  →  HCL 打开该副本  →  HCL 自行 create/create_udp 重建画布  →  HCL 保存  →  回读 .net + 查询后端
```

- 只有"打开/保存"这一个动作走窗口自动化，而且它**已经被证明可行**；其余全部是文件与协议，确定性可测。
- 编辑类 9 项（`add_device`/`delete_device`/`move_device`/`rename_device`/`set_port`/`add_link`/`delete_link`/`add_module`/`install_modules_batch`）先用 relay 实现：语义是"改文件 → 重新载入"，对使用者的可见行为是工程被重载。
- 注释 2 项（`add_note`/`clear_annotations`）本来就在 `.net` 的 `[Non-vBox-DATA]` 里（实测有 4 个 `[[NOTE n]]`），属于纯文件编辑，可以直接做。
- **开放问题**（值得一次实验）：后端 `create`/`delete` 之后，GUI 是否存在重新读取后端拓扑的动作。若有，增量编辑可以完全绕开窗口自动化。

**验收**：每次编辑后 `query_topology` 与 `.net` 回读一致；源工程哈希不变；操作与请求绑定。

### P4 — 让 guest 真正启动（用户触发）

这是唯一需要动 Windows 启动/安全配置的环节，且**已有既定方案**：`scripts/hcl_lab_boot.ps1` 创建独立实验启动项、先备份 BCD、只对副本关闭 Hypervisor/VSM、不自动重启。仍缺的是**专项确认**与用户手动重启。

**验收**：启动一台设备后，`create_udp` 拿到的管道能读到 Comware 提示符；不追加任何长测试，只跑剩余必需门槛。

> **进展（2026-10-01）**：使用者启用 Windows 11 内置 `sudo`（本机为**强制新建窗口模式**，提权动作必须用文件回执取结果）并作为设备所有者授权后：
>
> 1. 实验启动项**已创建并回读验证**（`hypervisorlaunchtype Off` / `vsmlaunchtype Off`，BCD 已先备份，`{current}` 与 `default` 均未变）。
> 2. 第一次重启尝试**没有真正进入实验项**：会话内 `bcdedit {current}` 仍是 `Windows 11` / `Auto`，`HyperVisorPresent=true`，`systeminfo` 也显示自 2026-09-30 起未重启。只读判定脚本给出 `not_booted_into_lab_entry`，随后按计划回退删除条目——**当次没有产生任何因果关系结论**。
> 3. 归因：启动菜单 `default` 是 `{current}`、`timeout` 30 秒，实验项被追加在最后，"人工在菜单里抢时间"会静默失败。
> 4. 因此 `hcl_lab_boot.ps1` 增加 `Arm`/`Disarm`，改用**一次性引导**（`bootsequence`）：下次启动直接进实验项、启动后自动清除、`default` 不动。本机 `{fwbootmgr}` 拒绝该设置，已改为在 `{bootmgr}`/`{fwbootmgr}` 间自动择一；现已在 `{bootmgr}` 武装并回读（回执 `ae5381b1…`）。
>
> **下一步只等使用者用「重启」（不是「关机」——快速启动会跳过引导流程）进入实验项**，然后跑 `scripts/hcl_lab_environment.ps1` 判定。
> **"引导项设置正确"仍不等于"guest 一定能起来"**，因果确认要等真正启动一台设备。详见 [控制平面实现与交接](control-plane.md) §10。

### P5 — D2 的 24 项 CLI 家族

有了 P2 的管道客户端和 P4 的可用 guest，这一层是**批量工程**而不是研究：`apply_*`（VLAN/STP/端口安全/加固/接口调优/ACL/NAT/NetStream）、`read_vlans`/`read_qos`/`inspect_ports`、`audit_security`、`backup_config`、`verify_connectivity`（真实 ping，必须解析丢包）、`diff`、`health_check`、`send_raw`、`deploy`/`full_build`/`live_deploy`。

**共同验收**：每条配置命令都要 CLI 回读；`deploy` 必须能报告"哪几条下发成功、哪几条被固件拒绝"；`verify_connectivity` 不能用"命令返回 0"代替丢包统计。

### P6 — 收口

- 3 项仿真语义：维持 unverified，写清"HCL 无原生逐事件回退/逐 OSI 层决策日志"，不推断、不冒充。
- `screenshot`：单模态 Agent 无法验收图像内容；要么把验收交给有视觉的一方，要么改成结构化导出（元素树/几何/状态）并明确声明它不是像素等价。
- 每项 implemented 都必须带 `verified_scope` 和回执路径；`parity_report.completion` 才能从 `incomplete` 走向可度量。

---

## 7. 与旧计划的差异

旧计划（交接文档 §11）的顺序是"先补实时门槛 → 再封装适配层 → 再补目录/计划/生成"。本路线图的差异：

| 旧 | 新 | 理由 |
| --- | --- | --- |
| 实时门槛是所有工作的前置 | 只有 D2 依赖实时门槛 | 14 项 D0 与 19 项 D1 都不需要 guest 启动 |
| 适配层建立在前端 UI 自动化上 | 建立在后端协议 + 控制台管道上 | 前端自动化成本随动作数线性增长且已验证脆弱 |
| 先封装适配层，再补目录/生成 | 先补 D0 离线层 | D0 零依赖、可立即回归，先把 61 项的"可度量分母"做大 |
| 计划校验只做结构 | 补服务参数校验 | 服务意图保存 ≠ 服务可用，是目前最大的语义空洞 |

---

## 8. 风险与明确不做的事

**风险**

- 后端协议是**未公开接口**，随 HCL 版本变化可能失效。缓解：白名单 + 版本探测 + 失败回执；只针对 5.10.3 声明支持。
- 后端直接改拓扑而 GUI 不刷新会造成**双真值**。缓解：relay 架构下一切变更都经 HCL 载入；后端写入动词默认关闭。
- relay 会把使用者的当前画布**重载**。缓解：只在独立副本上操作，默认不碰源工程。
- P4 会让该会话失去 Hypervisor/VBS 防护。缓解：独立启动项、BCD 备份、不自动重启、可一键删除。

**不做**

- 不把像素坐标、旧 PID、旧句柄复用为通用能力。
- 不把 LLM 识图或固定像素当作产品级控制面。
- 不静默关闭 Windows 安全功能，不自动重启。
- 不把"配置已生成"说成"配置已下发"，不把"命令返回"说成"网络连通"。
- 不推断 Packet Tracer 的逐事件仿真语义。

---

## 9. 建议的下一步（Top 5）

1. **P0 契约硬化** —— 地基，成本最低，测试已就绪。
2. **P1 目录 2 项 + 3 个资源** —— 一天内可把 implemented 从 4 提到 9。
3. **P1 规划 4 项** —— 纯计算层，把 validator 从"结构检查"提升为"可解释、可修复、可估算"。
4. **P2 后端适配层只读部分** —— 先只加 `create_topology`/`set_hcl_tcp` 之类可回读的动词，拿到"能看见拓扑生命周期"的能力。
5. **P3 注释与 relay 最小闭环** —— `add_note`/`clear_annotations` 零风险先落地，再验证 relay 的可用性。

需要用户决策的两件事：**是否批准基于未公开后端协议实现控制平面（P2）**，以及**是否执行实验启动项修复（P4）**。
