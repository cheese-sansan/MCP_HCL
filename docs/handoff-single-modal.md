# MCP_HCL：面向单模态 Agent 的交接

> **状态：已归档（2026-10-01）。** 本文是某个时间点的交接快照，保留当时的证据与限制，**不再作为当前事实来源**。
> - 当前目标、差距分析、依赖分类与实施顺序见 [路线图](roadmap.md)（本文 §11"后续推进顺序"已被其取代）；
> - 控制平面决策见 [ADR-0001](adr/0001-live-control-transport.md)；
> - HCL 后端协议的可观测细节见 [后端协议观察记录](hcl-backend-protocol.md)；
> - 本文 §7 的最小纯 MCP 验收步骤仍然有效，已由 dsh 分支上的契约测试固化；
> - 本文中已被本轮实测更正或补充的条目，见文末[归档时的更正与补充](#归档时的更正与补充2026-10-01)。

更新日期：2026-10-01（Asia/Singapore）。项目目录：`E:\MCP_HCL`。

本文面向不能识别图像、不能直接操作电脑的新 Agent。下一步任务是通过纯文本 MCP 评估实际可用性。本文只交接事实和已有授权，不授权额外的系统修改、重启、提交或发布。

## 1. 当前结论

**完整 MCP 实时闭环尚不可用，上游功能移植未完成。** 当前可以通过 MCP 读取工程、读取本地型号资料、校验部分计划，以及生成独立阶段工程。不能通过公开 MCP 接口打开/保存当前 HCL 画布、启停设备、执行 CLI、真实 ping 或抓包。

- 版本 `0.1.1`，实际注册 **11 个工具、3 个资源**；没有注册空壳实时工具。
- 固定上游提交 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d`，清单涵盖 **61 工具、5 资源**。机器清单的工具状态为 **4 implemented / 54 planned / 3 unverified**，资源为 **2 implemented / 3 planned**。
- 11 是实际 HCL 工具数，4 是上游条目实现数，两者口径不同：阶段替代及辅助接口不能计作实时等价；计划校验虽然已注册，但完整服务校验尚待完成，映射中仍为 planned。
- 历史桌面子门槛证明副本打开/保存、设备新增、链路增删；它们通过外部辅助脚本完成，**不是当前 MCP 已暴露相应动作的证据**。
- 实时门槛失败于设备启动，VirtualBox 报 `VERR_NEM_VM_CREATE_FAILED`；设备删除未完成，真实 CLI 和网络连通未验证。
- 本次交接核对了代码、已有回执及副本文件，没有重跑桌面、启动、网络或全量测试。

新 Agent 应分别报告“连接与发现”“现有接口业务”“纯 MCP 实时闭环”“全部上游等价”。前两项通过不能推导后两项通过。

## 2. 目标、约束与授权

目标：在 HCL 5.10.3 中复现 [固定上游版本](https://github.com/Mats2208/MCP-Packet-Tracer/tree/846db381bc2c6ee0229d56e1d7ce8847eb6b213d) 的 HCL 功能等价能力，必须实时控制并回读。逐项实现、经证据确认的替代或明确不支持结论都要记录；完整61/5清单见 [逐项对照](upstream-parity.md)和 `src/mcp_hcl/data/upstream_parity.json`，不在本文重复全表。

必须延续：

- 默认保护原工程；修改只在副本，不分发 HCL 程序、镜像或用户配置。上游 MIT 代码如复用需保留署名。
- 使用 `.net` 与 Comware，不沿用 `.pkt`、IOS JavaScript 或不适用的 HTTP/file 桥假设。
- 后台执行但未同步画布、文件 staging、旧响应、焦点丢失、失败 ping 或丢包都不能报告实时成功。保留失败与请求关联证据。
- 用户要求**减少不必要测试**：已有成功回执沿用，只验证新风险、新客户端本次调用和剩余必需门槛；不要循环重试启动或重做已通过的画布步骤。
- 耗时超过一分钟的启动/网络验收由用户触发，提供命令并保存回执；重启由用户操作。
- 用户已允许直接调用同权限外部 PowerShell，并选择在本机修复兼容性后继续。但创建实验启动项、停用其 Hypervisor/VSM 的专项确认仍未收到，BCD 脚本尚未执行；不要静默关闭 Windows 安全功能。
- 未授权 commit、push、PR、发布、更换共享 VirtualBox 或删除历史回执。
- 先前 Cisco Packet Tracer 咨询邮件不构成许可、兼容性或授权证明。

**本次单模态测试的边界：** 不看图、不直接输入桌面，也不使用外部 PowerShell、VBoxManage 或内部 Python 模块代替缺失 MCP 工具。若另行使用辅助路径，单独记录，不能计入“仅 MCP 通过”。模型没有视觉能力不应成为掩盖接口缺失的理由。

## 3. 环境与启动

| 项目 | 当前核对或历史快照 |
| --- | --- |
| 仓库 / 分支 | `E:\MCP_HCL` / `codex/hcl-live-parity` |
| HEAD | `1005ac3fb455b69b4cbd07b4eaca4f16a3d94e8c` |
| 工作树 | 实现和文档未提交；不要 reset/clean 覆盖 |
| Python | 项目 `.venv`，3.12.14；本机无可用 `py` 命令 |
| SDK / Pydantic | 本机 1.30.0 / 2.13.5；约束 `mcp>=1.28,<2`、`pydantic>=2.11,<3` |
| HCL | 5.10.3，`D:\HCL`，进程 `SimwareClient` |
| VirtualBox | 6.0.14，`C:\Program Files\Oracle\VirtualBox` |
| 后端 | 历史 SimwareWrapper TCP16600、SimwareMultiCC TCP16500；当前进程需重新读取 |
| Windows | 历史 Windows11家庭版 build26200、HypervisorPresent=True、VBS运行；不是本次重新探测值 |

### 推荐配置：只允许测试隔离副本

这是常见 stdio MCP 客户端配置示例；不同客户端外层字段可能不同。环境变量必须传给 MCP 子进程。输出根目录会自动加入允许读取的根目录，可继续处理阶段结果。

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

等价启动命令（由客户端管理 stdio，不能在无关终端设置变量后假设客户端继承）：

```powershell
$env:MCP_HCL_PROJECT_ROOTS = 'E:\MCP_HCL\work\feasibility\gate_20260930'
$env:MCP_HCL_OUTPUT_ROOT = 'E:\MCP_HCL\work\staged'
$env:MCP_HCL_INSTALL_ROOT = 'D:\HCL'
$env:MCP_HCL_BACKEND_PORT = '16600'
& 'E:\MCP_HCL\.venv\Scripts\python.exe' -m mcp_hcl.server
```

stdio Server 等待协议输入，终端没有业务输出不代表卡死。使用真实 MCP 客户端；不要随意向 stdin/stdout 写普通文本。

默认：PROJECT_ROOTS 是当前用户 `HCL\Projects`，多根用分号；OUTPUT_ROOT 是启动工作目录下 `work/staged`；INSTALL_ROOT 是 `D:/HCL`。推荐使用绝对路径和上述副本限定配置。更换代码/配置后重启 MCP 子进程；若发现工具数量或初始化版本不符，先查旧进程、旧安装或环境变量。

已构建 wheel：`work/wheels/mcp_hcl-0.1.1-py3-none-any.whl`，SHA256 `EDB792C2F27007A8B57235E8832ADE502FBA2CC2DA70E9BA573A2D07F9130BA8`。wheel 不包含外部 PS 脚本或 work 回执。曾遇 PyPI TLS EOF，本机可用已有运行时 `pip wheel --no-deps --no-build-isolation`，不要无目的重新下载依赖。

## 4. 当前全部工具

以客户端实际发现的参数 schema 为准，下表来自当前 `server.py`。

| 工具 | 输入 | 行为及局限 |
| --- | --- | --- |
| `hcl_capabilities` | 无 | 当前能力/注册清单；不是实时状态，无统一 status 外壳 |
| `hcl_list_projects` | 无 | 列根目录下一层有效工程，不递归；只返回 projects |
| `hcl_inspect_project` | `project_path` | **接受工程目录，不接受.net文件**；读取保存设备/坐标/链路，status=ok不是运行态；不返回注释正文、配置正文、端口状态或VM电源 |
| `hcl_stage_copy` | `project_path,stage_name` | 创建独立副本、重写工作目录和工程名；staged，不打开画布，不是通用全目录归档 |
| `hcl_stage_add_device` | 上述两项，加 `template_device,new_name,x,y`；可选 `connect_to,connect_to_port,new_port` | 克隆已有模型字段、可同时连线；三个可选连线参数必须一起提供；新CFG为空，不复制模板运行配置；不核对型号是否实际拥有场景端口 |
| `hcl_stage_link` | `project_path,stage_name,a,a_port,b,b_port` | 副本写双端连接，只检查格式、名称、占用；无电源、线缆完整兼容或实时效果 |
| `hcl_parity_report` | 无 | 固定61/5映射及真实注册面；verified仅inventory，completion=incomplete，planned名称不能调用 |
| `hcl_bridge_status` | 无 | 本机后端版本/内存及请求ID回读；不包含工程、电源或CLI；可能返回partial/unverified |
| `hcl_list_devices` | 无 | **型号目录，不是当前拓扑设备列表**；来自本地default CFG，附接口/版本字符串/哈希；不保证覆盖GUI全部型号，不证明guest固件版本 |
| `hcl_get_device_details` | `model` | 一个已安装型号的默认资料；未知型号/安装缺失可返回partial，不是运行设备查询 |
| `hcl_validate_plan` | `plan`对象 | 版本化结构及部分端口/地址语义；valid=true不证明完整服务参数、固件命令、部署或连通性 |

原5工具为兼容保留旧结构；统一状态、目标工程、操作ID、证据字段尚未覆盖全部旧接口。不要假设每个结果均有 operation_id、target_project、evidence，也不要把 MCP `isError=false` 等同业务成功。部分损坏工程可能抛工具错误而不是业务rejected。

### 资源

| URI | 内容 / 局限 |
| --- | --- |
| `hcl://capabilities` | 与能力工具一致的JSON文本，不是运行态 |
| `hcl://catalog/devices` | 本机默认型号目录，runtime_verified=false |
| `hcl://catalog/ports` | deviceInfo.ini端口族/索引；尚非所有型号已验证的CLI/场景映射 |

ports是HCL新增资源，不等于补齐上游别名/线缆/模板资源。客户端若只支持tools而不支持resources，应单列资源接入缺口。

### 状态口径

| 状态/字段 | 可以声称什么 |
| --- | --- |
| `ok` | 旧式保存工程检查完成，无实时含义 |
| `staged` | 独立文件生成，当前画布未改变 |
| `verified` | 仅verified_scope限定的层通过；目录、计划或后端回读不是部署成功 |
| `partial/unverified` | 部分失败/证据不足，读取error与evidence |
| `rejected` | 请求或校验失败 |
| `input_sent`（辅助回执） | 发送过输入，须有后续回读才能认定效果 |
| `runtime_verified=false` / `full_live_gate_passed=false` | 不得声明运行态或完整实时门槛成功 |

生产化的实时执行/等待回读状态机尚未完成；所有未支持能力的终版结论也未完成。设计中的状态不是已实现行为。

## 5. 文件和领域模型的限制

### 工程与阶段写入

- 针对已观察HCL5.10.x UTF-8/BOM ConfigObj风格.net；目录必须有有效project.json和恰一个.net，不保证兼容所有版本或损坏变体。
- 保留未知字段、已有中文名与Non-vBox注释文本；检查已识别设备重复字段/ID、已识别链接对称性。未知外部端点可被链接汇总略过，数量不能证明所有原始字段有效。
- 副本包含.net、project.json、deviceversion.txt、ConfigDisk、DeviceConfig及存在时的SerialFile；不复制任意README/Git/PNG/ZIP。不是完整工程导出/归档。
- 有源/输出根限制、指定文件和目录树的symlink/junction检查、临时目录组装后rename；不是整个未知字段/路径的完整安全审计。PS打开探针还会核对配置路径和workingdir。
- stage_name首字符ASCII字母，总长1–20，后续字母/数字/下划线；拒绝已有阶段，不覆盖，无幂等键。失败重试先检查目标，不盲目造副本。
- 新设备名首字符ASCII字母，总长1–32，后续字母/数字/下划线/连字符；已有名按大小写不敏感检查。已有中文名能保留及作模板/对端，但阶段新增暂不接受中文名。
- 阶段坐标有限且绝对值≤10000。大配置盘可能复制很慢，没有异步进度或取消接口。
- stage_copy公开证据目前是保存文件路径，无完整源/目标哈希工具。纯MCP设备数量不变不能证明文件逐字节未变。

### 端口与型号目录

- staging使用.net键，如GE_0/0；计划用Comware名，如GigabitEthernet0/0。不能混用或把MSR上的映射推广到所有模块/型号。
- 当前目录资料8个默认CFG型号、11个端口族；可能遗漏无默认CFG的GUI型号，默认CFG版本与实际镜像版本不是同一证据。
- 默认接口可能包含NULL0、管理口等；计划显式拒绝NULL0，但不能证明其他全部接口可在画布连接。

### TopologyPlan v1

字段：name、devices、links、addresses、routes、services、annotations。拒绝结构中未知字段；设备ID为ASCII标识，展示名可中文，坐标不接受非有限数。示例见 [Agent指南](agent-guide.md)。

已实现：重复ID/名称、设备/型号/默认接口引用、重复端口、自连接、serial/ethernet类型、重复IP、同接口同地址族重复、IPv4网络/广播地址、路由地址族检查。

未实现：计划持久化、从工程导出完整计划、计划一键转换.net、自动修复/估算/解释、完整网段/网关可达性/VLAN/VRF/路由邻接/无线语义。每接口每地址族只允许一条地址，尚不表达完整secondary address情况。

services保存DHCP/OSPF/RIP/VLAN/ACL/NAT/security/wireless/QoS/NetStream意图和参数，但参数未做完整协议校验，不生成或下发配置；会返回feature_runtime_unverified。IPv6地址/路由基础校验不代表IPv6运行可用。

## 6. 实时门槛与故障

### 工程和已取得的证据

源工程在当前用户 `HCL\Projects\v7_sw_vlan_basic`，基线5设备/4链路/4注释；名为PC的3节点实际是MSR36-20。原.net历史SHA256：`CCC821A5FBA6F30AE0F20CBB5FB4029D39A9D5812068B6B40047A1E85A785570`。

实时副本：`E:\MCP_HCL\work\feasibility\gate_20260930\v7_sw_vlan_basic`，项目名MCP_HCL_Gate_20260930。本次文件只读核对为**6设备/4链路/4注释**；测试MSR36-20_6仍在，新链路已删除。没有重新观察本次窗口或VM电源。

| 子门槛 | 历史结果 / 限定范围 |
| --- | --- |
| 同权限Qt树访问 | 成功；中权限曾错误5拒绝，普通原生点击也未产生效果 |
| 打开副本、核对工程名与目录、保存回读 | 成功；外部辅助脚本，不是公开MCP动作 |
| 新增设备 | 成功，5/4→6/4 |
| 新增链路 | 成功，6/4→6/5，路由器GE_0/0到核心GE_0/2 |
| 删除新增链路 | 成功，6/5→6/4，4注释保留；菜单特征+保存回读 |
| 删除测试设备 | 未完成，仍有6设备 |
| 启动测试设备 | 失败，VM回到poweroff，没有运行guest |
| 停止运行设备 | 未验证，没有成功启动前提 |
| CLI / ping /抓包 | 未验证，没有真实运行输出 |

VM6历史名topo1-device6、UUID `18708cf7-ede7-4034-9693-ce1d1590b064`，位于当前用户HCL VMs\topo1\device6；配置盘指向副本ConfigDisk\device6.vdi。UART2是服务端管道 `\\.\pipe\topo1-device6`，UART1是SerialFile文本文件。仅传输配置证据：**没有已实现/验证的MCP named-pipe CLI适配器**。

### 当前故障和待确认修复

日志：VidStartVirtualProcessor错误87、CPUM无hardware-virtualization capability、VERR_NEM_VM_CREATE_FAILED、E_FAIL(0x80004005)；HCL后续session busy重试和设备启动失败。最后历史观察所有VM关机，不是成功启动。

只读快照有HypervisorPresent=True、VBS运行、BCD hypervisorlaunchtype Auto、固件虚拟化已启用；不能据此认为BIOS虚拟化未开。Secure Boot及加密也有历史快照，可能随环境变化。

[官方5.10.3安装说明](https://www.h3c.com/cn/d_202404/2116237_30005_0.htm)及具体修复命令见 [实时门槛文档](live-gate.md)。`scripts/hcl_lab_boot.ps1`已准备创建独立MCP_HCL Lab启动项，先备份BCD，仅副本Hypervisor/VSM Off，保留日常默认，不自动重启。**尚无Create执行回执、尚未获专项确认、修复效果未验证**。用户选实验项时该会话的VBS相关防护及Hyper-V依赖功能不可用。

### 桌面适配器开发踩过的点

- PS5.1中文JSON默认编码失败已通过显式UTF-8修复，失败回执保留。
- Qt主窗口用同PID的Workspace识别；原生#32770文件选择框可能为桌面顶层，不只在主窗口后代中。模态可能改变MainWindowTitle/Handle。
- 文件编辑用Unicode WM_SETTEXT/GETTEXT及有界SendMessageTimeout；旧SendKeys不可靠。发送输入须配合回读。
- 画布平移后固定像素曾命中注释，未执行误删；根据滚动条/缩放/场景位置投影后核对菜单特征才删除。重复源端口被HCL拒绝“无法连接同一接口”，负面记录保留。
- geometry.py只验证MSR36-20、S5820V2-54QS-GE的50场景单位图标。旧PID、句柄、坐标不能复用。
- 曾遇LockApp，指针归属保护拒绝操作。锁屏/未知焦点不能继续输入，不自动解锁。
- work/feasibility的桌面脚本是原型，部分固定对象/坐标、旧latest可能残留，无通用生产broker；不能批量盲跑或直接包装成通用MCP工具。

未来可在服务端内部实现可靠结构化桌面控制，单模态LLM无需看图。当前缺的是已验证、可发现、有回读的MCP适配层。

## 7. 新 Agent 的最小纯 MCP 验收

以下**待新客户端执行**，并非已替它执行。每项通常一次；保存参数、协议错误、业务结果和范围到新的work回执/报告，不覆盖历史。

### A：连接与只读

1. 初始化，保存实际tools/resources及版本。预期11/3、0.1.1。
2. 调用capabilities、parity_report，读capabilities资源。61/5是映射项数，不能当作注册数；预期incomplete、full_live_gate_passed=false。
3. list_projects，再inspect实验**目录**：

   ```json
   {"project_path":"E:\\MCP_HCL\\work\\feasibility\\gate_20260930\\v7_sw_vlan_basic"}
   ```

   文件当前6/4；若不同，以新回读为准并调查修改。
4. list_devices、get_device_details（`{"model":"MSR36-20"}`），读两个目录资源。8/11是本机快照，不是任意安装的协议常数。
5. bridge_status一次。历史版本1.0.0&6.0.14、内存14708MB；内存非固定验收值。partial/unverified记为当前后端不可达或回读失败，不循环重试或宣称实时控制成功。

### B：计划

使用agent-guide中的两路由器计划调用validate_plan，预期valid=true、runtime_verified=false。复制输入并重复一条link后再调用一次，预期rejected/valid=false、duplicate_port。含services的警告不是服务配置通过。

### C：三个阶段接口

会写新副本但不打开HCL、不启动设备。阶段名若已存在则换唯一有效名，不删除旧结果。

1. stage_copy：

   ```json
   {"project_path":"E:\\MCP_HCL\\work\\feasibility\\gate_20260930\\v7_sw_vlan_basic","stage_name":"TextCopy_1001"}
   ```

   预期staged、6/4。以返回project_directory调用inspect，不能传project_file。
2. stage_add_device：

   ```json
   {"project_path":"替换为上一步返回的project_directory","stage_name":"TextAdd_1001","template_device":"PC1_3","new_name":"TextR7","x":300,"y":300}
   ```

   必须替换示意动态路径。模板实际MSR36-20；预期7/4，inspect回读。
3. 确认TextR7和MSR36-20_6的GE_0/0空闲后stage_link：

   ```json
   {"project_path":"替换为新增设备结果的project_directory","stage_name":"TextLink_1001","a":"TextR7","a_port":"GE_0/0","b":"MSR36-20_6","b_port":"GE_0/0"}
   ```

   预期7/5，inspect回读端点；若基线变动，使用已知型号实际空闲端口，不沿用历史假设。
4. 再inspect本组源，拓扑应不变。当前MCP无源哈希工具，不能声称因此证明逐字节不变。

### D：完整性判定

任务若要求“当前画布构建→启动→配置→真实ping”，先检查对应工具是否存在。当前不存在，应记录**纯MCP完整实时任务Incomplete：缺少接口且guest历史启动失败**，不必再次运行长测试证明同一缺口。

HCL抓包只是数据包观察候选，尚未实现验收。PT逐事件回退/逐OSI层决策日志没有HCL原生等价证据，三项仿真条目保持unverified；推断解释不能冒充原生日志。

报告模板：

| 层 | Pass/Fail/Incomplete | 实际接口/状态 | 新回执 | 限定范围 |
| --- | --- | --- | --- | --- |
| 连接与发现 | 待本客户端测试 | — | — | 本次进程 |
| 已注册只读接口 | 待测 | — | — | 文件/目录/后端 |
| 计划校验 | 待测 | — | — | 已实现检查 |
| 阶段生成与回读 | 待测 | — | — | 保存文件层 |
| 纯MCP实时闭环 | 当前Incomplete | 无电源/CLI/画布工具 | 另保存本客户端发现清单 | 当前实现 |
| 全部上游等价 | 当前Incomplete | planned/unverified尚存 | parity_report | 固定61/5 |

## 8. 文本证据索引

路径相对E:\MCP_HCL。work被Git忽略，换机器/仅clone不会存在；先确认文件存在。历史JSON/log不是当前实时状态。单模态Agent可读文字配套文件，不能声称自己审核了png内容。

| 文件/目录 | 范围与限制 |
| --- | --- |
| `work/feasibility/stdio-stage-copy-20261001.json` | 真实stdio副本、当时源非Git文件哈希及source_unchanged=true；旧响应结构可能缺新增操作ID |
| `work/feasibility/backend-status-20261001.json` | 后端两项回读，不证明画布/CLI |
| `work/feasibility/open_gate_20261001/result.json`及`runs/` | 最新子门槛、独立成功/失败历史；full_live_gate_passed=false |
| `work/feasibility/step-runs/` | 原型步骤stdout/错误、脚本哈希、运行记录 |
| `work/feasibility/projected-link-context-result.json` | 历史视口投影、菜单特征 |
| `work/feasibility/menu-invoke-result.json` | 删除input_sent，仅结合之后保存回读才计效果 |
| `work/feasibility/environment_20261001/92ba4f26c1db4cd58ac21ea012192366/result.json` | 环境/BCD/VBS/VM只读快照 |
| 同目录`device6-VBox.log` | 保存的失败日志，SHA256 `F1360EC27A2AA036E524369593D5B9BD9CF70B857459CA99DB24E67185B49F30` |
| `work/feasibility/catalog-20261001.json` | 默认型号/端口快照，非guest能力 |

## 9. 测试历史与不足

- 历史离线13项通过；后补几何4项及UTF-8脚本预检1项通过。
- 目录2、计划3、stdio1、映射3这一组9项通过；结果字段改动后只重跑受影响stdio1项通过。存在重复，不要相加为独立用例数。
- 当前源码22个测试方法，未在全部最终修改后全量重跑22项；本次文档整理也未重跑。
- stdio现有测试证明初始化、发现、capabilities资源和parity调用，不是11工具均已在真实HCL业务环境逐项验收。
- 工程测试用合成文件；后端部分用模拟TCP peer；门槛脚本测试仅ValidateOnly，不操作桌面；几何只覆盖两个观察模型。
- 已构建wheel；未取得61项运行验收、真实ping、完整故障回滚和安全审计证据。按具体改动/剩余风险追加测试，别以离线测试代替实时证据。

## 10. 代码和文档地图

| 路径 | 用途 |
| --- | --- |
| `src/mcp_hcl/server.py` | stdio工具/资源、环境配置、业务错误包装 |
| `project.py`（同目录） | .net解析、路径保护、模板克隆、阶段提交 |
| `backend.py` | 两项白名单loopback查询，请求ID、65536字节上限、单请求默认2秒截止时间；不是任意后端命令入口 |
| `catalog.py` | 本地CFG/INI读取、文件来源哈希，不内嵌厂商文件 |
| `topology.py` | Pydantic v1计划及局部校验 |
| `geometry.py` | 局部画布变换，尚未接入实时MCP |
| `parity.py`与`data/upstream_parity.json` | 注册集合、61/5清单和来源指纹 |
| `scripts/hcl_open_gate.ps1` | 同权限隔离工程打开/保存、ValidateOnly和显式恢复选项；非MCP接口 |
| `scripts/hcl_environment_snapshot.ps1` | 只读环境快照/日志；非MCP接口 |
| `scripts/hcl_lab_boot.ps1` | 待批准的实验启动项Create/Remove；非MCP接口 |
| `tests/` | 工程/后端/目录/计划/清单/几何/预检/stdio |
| [README](../README.md)、[Agent指南](agent-guide.md)、[逐项对照](upstream-parity.md)、[实时门槛](live-gate.md) | 安装、输入示例、完整映射、历史及修复命令 |

work/upstream保留上游注册源码；权威基线仍为固定提交。LICENSE为MIT；当前只提取接口名/映射，没有移植上游运行代码。

## 11. 后续推进顺序

1. 新单模态客户端按第7节测试现有MCP、记录分层结论；不以外部桌面行为补齐接口。
2. 若用户继续修复，取得实验启动项专项确认后执行，保存GUID/备份/回读，用户自行重启；更新“未执行”状态。重启后重读环境，仅检查剩余电源门槛。
3. 在副本完成设备删除、启停、CLI回读及必要连通性。named pipe须绑定工程/VM/请求、拒绝旧输出，不允许任意宿主管道或强制抢占会话。
4. 将已验证动作封装成受限、本机、同权限、可回读的HCL控制适配层，并提供实际MCP接口。不要依赖LLM识图、固定像素、任意宿主shell或无认证高权限broker。
5. 补全型号端口映射、别名/线缆/模板目录、计划修复/估算/解释、导入导出与一键构建。完成Comware地址/DHCP、路由、VLAN、ACL/NAT、安全、IPv6、无线、QoS、NetStream生成及实测下发；服务意图保存不算配置实现。
6. 补齐配置备份、端口/VLAN检查、真实ping、差异、安全审计、抓包；协议按设备固件探测。PT专有能力有原生证据才能等价，否则明确不支持/未验证及推断来源。
7. 同步真实注册清单、能力报告、61/5映射与结果语义，保持旧5接口兼容；只补必要测试，最后重新用纯MCP单模态客户端验收。

### Suggested skills

- api-and-interface-design / tool-use-schema-design：接口参数、统一结果与兼容变更。
- tool-failure-handling：请求关联、截止时间、幂等、部分失败与回读。
- documentation-and-adrs：适配层、权限broker、CLI传输的实际决策。
- handoff：更新交接事实，按用户要求保存在项目内。
- computer-use：仅另行开展桌面适配器开发时；本次纯MCP单模态测试不依赖此技能。

### 可直接给新 Agent 的开场指令

> 读取E:\MCP_HCL\docs\handoff-single-modal.md。你的本次任务是用纯文本MCP测试现有MCP_HCL实际可用性。先核对连接、实际工具/资源和边界，按最小流程调用并保存新回执，输出分层结果。不要识图、直接操作桌面或用外部shell替代缺失MCP工具。不要改原工程、Windows安全/启动设置或自动重启。沿用已有成功回执，只补必要测试。实时闭环缺工具或设备启动失败时报告Incomplete，区分接口缺失、客户端配置、权限与运行环境原因。

---

## 归档时的更正与补充（2026-10-01）

本节由 `dsh` 分支的单模态验收与契约测试补充，回执见 `work/feasibility/single-modal-20261001/` 与 `work/feasibility/dsh-20261001/`。

### 新增事实

- 协议握手为 `protocolVersion=2025-11-25`（本文未记录）。
- `resources/templates/list` 返回 **0** 项；上游 5 个资源中 `aliases`/`cables`/`templates` 仍为 planned，印证 §4 的"ports 资源不等于补齐上游缺口"。
- `prompts/list` 返回空列表，但 capabilities 中声明了 `prompts` 能力。
- `hcl_list_devices` 与 `hcl://catalog/devices` 的负载**除 `operation_id` 外逐字段一致**；但 `operation_id` 每次调用都会重新生成，**不是可跨接口关联的稳定键**，因此尚不满足"请求关联证据"的要求。
- `hcl_stage_copy` 的保真度高于本文描述：副本 `.net` 与源**只差 `workingdir` 一行**，未知字段、中文设备名、注释块与 `[Non-vBox-DATA]` 全部保留。
- 实测 `D:\HCL` 与本用户工程的 `.net` 均为**无 BOM + CRLF**；读取端接受 BOM，写回端不写 BOM。
- 本机 shell 是 Windows PowerShell 5.1、默认 ANSI 为 `gb2312`。对阶段工程的 `project.json` 执行 `Get-Content -Raw | ConvertFrom-Json` 会解码损坏并解析失败，需显式 `-Encoding UTF8`。这与 §6 已记录的 PS5.1 编码问题一致。
- 原受保护工程 `.net` 的 SHA-256 仍为 `CCC821A5FBA6F30AE0F20CBB5FB4029D39A9D5812068B6B40047A1E85A785570`，与本文一致；其实验副本的 `.net` 与 `project.json` 修改时间均早于本次客户端运行。

### 更正

- **§4/§7 的 `isError` 语义需要补上互补的一半**：本文写了"不要把 `isError=false` 等同业务成功"，但反过来 **`isError=true` 也不等于 HCL 业务失败**。缺少必填参数、参数类型错误、未知工具名都会返回 `isError=true`；真正的业务失败是 `isError=false` + `status=rejected`。客户端必须同时看两者。
- **§5 关于注释**：`hcl_inspect_project` 不返回注释，但注释就在 `.net` 的 `[Non-vBox-DATA]` 段中（该工程实测 4 个 `[[NOTE n]]`）。缺的不是数据，而是**没有 MCP 工具暴露它们**——这也意味着 `add_note`/`clear_annotations` 属于纯文件编辑，不需要实时能力。
- **§4 状态口径**：结构错误时 `errors[]` 是 pydantic 原始形状 `{type, loc, msg, url}`，**没有 `code` 键**；只有语义错误才是 `{code, message}`。按 `code` 分支的客户端会在结构错误上取不到键。
- **§5 关于损坏工程**：本文只笼统提到"部分损坏工程可能抛工具错误"。本轮定位到两个可复现形状：`device_id = abc`、`x = not-a-number` 会因 `int()`/`float()` 未被包裹而以工具错误逃逸，而不是业务 `rejected`。缺 `[vbox]`、两个 `[vbox]`、缺 `device_id`、重复字段、非对称链路、非 UTF-8 都已正确返回业务 `rejected`。
- **未知参数被静默忽略**：`hcl_stage_copy` 带一个不存在的参数名仍返回 `staged`。因此 `hcl_stage_add_device` 的可选连线参数若拼错（例如 `connect_to` 写成 `connect_too`），会走"只加设备"的分支并返回成功，**静默产生半成品**。

### 未验证项（不得记为通过）

- **符号链接防护**：本机账号无 `SeCreateSymbolicLinkPrivilege`（`OSError [WinError 1314]`），相关测试被 skip。该防护属未验证，不是通过。
- **后端版本与内存回读**：本轮 `hcl_bridge_status` 返回 `status=unverified`（本机无 `SimwareClient` 进程，后端 16600 在 2.01 s 截止时间内未响应）。因此本文 §3 表中的 `1.0.0&6.0.14` 与 `14708` MB 属**历史快照**，未在本次复现，也不应作为固定验收值。
- **实时闭环**：发现面中画布/电源/CLI/ping/抓包工具为 0 个，结论仍为 Incomplete（接口缺失）。

### 测试状态

本机测试基线更新为 **38 项全部通过**（原有 22 项 + `tests/test_mcp_contract.py` 新增 16 项，1 项因 symlink 权限 skip）。本文 §9 记载的"22 项未在全部最终修改后全量重跑"这一遗留项已闭合。
