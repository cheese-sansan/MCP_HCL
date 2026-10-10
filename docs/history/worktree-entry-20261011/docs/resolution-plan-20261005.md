# MCP_HCL 后续解决方案

日期：2026-10-05（Asia/Singapore）。依据 `HANDOFF.md` §17–18、原始试验回执、当前只读环境与源代码检查。本文件是实施方案；所列修复和真实验收尚未执行。

## 1. 决策与当前基线

执行顺序：**确认代码基线 → 在 HCL 启动前建立运行时隔离 → 修复控制台诊断与访问合同 → 单设备 CLI 回读 → 同型号网络闭环 → 混合型号验证**。

离线软件工作可先推进；任何真实 HCL/guest 操作必须先满足隔离门槛。备份是恢复资产，不能替代隔离。

本轮核实：

| 项目 | 当前事实 | 证据边界 |
| --- | --- | --- |
| 指定源仓库 | `E:/MCP_HCL`，`dsh-2`，HEAD `e7231a3b4139219910af2bb84901aedd71bae986`，包版本 0.1.1 | 读取前工作树干净 |
| 当前聊天工作区 | `C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL`，detached HEAD `1005ac3fb455b69b4cbd07b4eaca4f16a3d94e8c`，包版本 0.1.0 | 不能用此工作区代表 dsh-2 或其他 Codex 分支 |
| VirtualBox | `6.1.50r161033`，仅注册原 `Simware_Base`，UUID `7ac3bddb-1356-4121-b70a-fd14a8bd8a94`；runningvms 为空 | 没有启动 guest |
| HCL/控制台进程 | 未发现 SimwareClient、SimwareWrapper、SimwareMultiCC、PuTTY、VBoxHeadless、VirtualBoxVM | 本次只读查询时的快照 |
| 恢复资产 | 完整备份目录存在；其 `HCL VMs` 子目录内 52 个清单文件均存在，另有 VirtualBox.xml 和 backup-manifest.json | 本轮只核对存在性；52 文件字节一致来自先前恢复回执，没有重复全量哈希或验证 guest 配置恢复 |
| 已有真实能力 | 单台 MSR36-20 创建与进入 guest 系统阶段已有成功证据 | CLI、配置、连通性、无线和完整 live gate 仍未通过 |

代码修复方案以指定仓库 dsh-2 为参照。实际开工前重新核对目标分支、HEAD 和改动；不直接在当前旧 detached checkout 写修复，不自动合并其他分支，不把旧测试数当作新版回归。

## 2. P0：在启动前隔离 HCL 运行时

### 问题与新发现

工程副本不同，但 GUI 仍分配 topo1，虚拟机落在 `C:/Users/w8p1p/HCL VMs`。历史实验发生 47 个旧文件缺失及原 Base 注册被移除。

原始 Wrapper 日志显示，`tryCleanLeftVMs` 在 Wrapper 初始化和 create_topology 时调用，normal_close/disconnect 也记录删除 VM 和目录。因此隔离门槛必须覆盖 **Wrapper 启动、工程自动加载、设备创建及正常退出**，不能只包住 MCP 写调用。

当前 `C:/Users/w8p1p/AppData/Roaming/H3C/HCL.ini` 有 `project_startup=true`，最近工程列表包含原工程；所见 project_directory 和 Capture.working_directory 不是已证明的 VM 根设置。尚未找到受支持的 HCL runtime 根重定向入口。

### 选择路线

1. 先只读确认 HCL 官方配置/入口、用户配置与已有日志中是否支持独立 VM 根、Base 和拓扑命名空间。只有可证明这些值实际被 Wrapper 使用时，才采用同用户下的隔离启动器。
2. 如果没有受支持入口，优先评估专用 Windows 实验账号：真实用户配置目录、HCL VMs、VBoxSVC 与注册清单都与当前账号分开。账号创建/首次配置及真实 HCL 操作属于后续明确授权步骤，本轮不执行。
3. 独立账号也不是自动通过：核实 HCL 是否仍触及共享厂商镜像、日志、TCP 16600 和 topo1 管道名。实验期间应避免两套 HCL 同时运行，不能把账号差异当作管道/端口隔离证明。
4. 若以上无法保护现有资产，真实实验转到专用实验机器；当前机器继续离线开发，不用暂时搬走原 VM 目录再恢复的方式冒充隔离。

`VBOX_USER_HOME` 是 VirtualBox 支持的配置目录切换入口，但只证明可切换 VirtualBox.xml 注册配置。结合本机日志，**单设这个变量不能证明 HCL VMs 根或厂商清理范围改变**。也不能假定已存在的 VBoxSVC 会读到新的启动环境。参考 [Oracle 6.1 配置与服务说明](https://docs.oracle.com/en/virtualization/virtualbox/6.1/admin/TechnicalBackground.html)。

### 建议的软件合同

增加只读 runtime preflight 和 manifest：记录真实用户身份、源 HEAD、project_path、operation_id、runtime_root、Base UUID、注册清单、磁盘引用、管道、端口及保护资产清单。隔离未证明或身份不符，返回 `runtime_isolation_unverified`，拒绝引导 HCL 和后续 live 写入。

manifest 只限定本工具的后续动作，不能阻止厂商自行清理共享目录；必须先完成真实隔离设计。清理仅针对本次清单内、路径和 UUID 都匹配的资产，不采用“关闭后删除所有 topo*”策略。

### 通过标准

- 一次打开/创建/启动/停止/退出全过程只触及本次独立 VM 命名空间。
- 历史工程、52 个原 VM 文件和原 Base 注册在前后保持一致；注册/磁盘清单没有预期外变化。
- 不自动载入当前账号的原工程，不与其他 HCL/PuTTY 会话冲突。
- 出现越界立即停止后续动作并保留证据；不自动重试，不扩大删除范围来“清理干净”。

## 3. P1：让控制台失败可归因、输出可验收

### 已知事实与静态风险

第二份真实读取回执为 PermissionError、0 字节、0 命令；没有保存 Win32 原始错误码，根因仍未确定。

保存的 .vbox 显示 UART0 为 RawFile，UART1 为 server=true 的 HostPipe `\\.\pipe\topo1-device6`。RawFile 不能替代双向 CLI 通道；BIOS、启动文本和自动配置画面不能替代命令回显与提示符。

dsh-2 的 ConsoleSession/HclConsole 代码还存在需要修正的静态风险：

- open/read/write 只保留异常类名，所有打开失败都在超时内重试。
- read_until_idle 在持续收到字节时直接 continue，可能绕过 deadline 检查。
- 超过输出上限时静默丢弃前部，不能证明输出完整。
- send 没有核对实际写入字节数；写入状态不明时不能重放整条命令。
- 管道格式校验不等于绑定本次 VM；当前没有跨调用的独占访问合同。

这些是源代码检查所得；本轮没有用真实 guest 复现。

### 修复设计

1. 打开层使用明确的 Win32 调用（CreateFileW，失败后立即保存 GetLastError），保留 `winerror/errno/api/stage/access_mode/elapsed`。错误分类至少含 not_found、access_denied、busy、broken_pipe、timeout、identity_mismatch。不要用试探多个访问模式或自动提权来绕过归因。
2. 明确读/写访问方式与 UART server/client 角色。只有已确认处于创建窗口的 not_found、busy 才允许有限等待；真正 access_denied 立即返回诊断。默认沿用约 2 秒打开预算，禁止无限重试。
3. 以 runtime manifest 内的用户、VM UUID、拓扑、device_id 和实际 UART endpoint 校验身份；身份不一致拒绝连接。独占租约覆盖跨 MCP 调用/进程，由同一读取者持有；外部 PuTTY/MultiCC 占用仍需实际确认，租约不能代表厂商客户端也遵守。
4. 不并发读取同一终端流。若确认被本次 GUI 控制台占用，在使用者确认后通过受支持操作释放本次控制台，再转交 MCP；不结束别人的终端。若 HCL 无受支持的独占交接，CLI 能力继续 blocked，单独评估受支持的控制台集成入口。
5. 每轮循环都检查总 deadline；明确 partial_write、timeout、truncated、prompt_missing、echo_missing。部分写入或命令发送后超时一律保留 outcome_unknown，不自动重发。超出上限保留统计并标记不完整，不返回可用于成功判定的完整输出声明。
6. 增加 connect/read 的诊断路径，复用同一独占租约；第一条真实命令选择已核对适用固件的只读查询（如 display version）。要求设备身份、命令回显、完整输出、结束提示符和时间线同时匹配。异步启动文本只计入 startup/stale 字节。

Microsoft 文档区分管道忙和访问方式不匹配：存在但所有实例占用时 CreateFile 返回 ERROR_PIPE_BUSY，错误码为 231。参考 [Named Pipe Client](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-client)、[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)、[系统错误码](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-)。这支持先保留原码再定因，不能由旧 PermissionError 推断本次一定是 busy 或 ACL。

### 软件与真实验收

软件用合成管道覆盖权限拒绝、被占用、端点未创建、断连、持续输出、截断、部分写入、陈旧数据、并发租约和身份错配，确保返回 typed error、严格超时、没有重复发送。随后运行所选代码基线的必要回归；不使用旧分支测试数代替新结果。

真实验收只在 P0 通过并由使用者触发后进行一次新的单设备查询，使用新 operation_id 和目录；成功仅提升 CLI 回读这一层。配置、网络和 full_live_gate_passed 仍保持 false，直到各自门槛独立通过。

## 4. P2：媒体 UUID 冲突先分类，再决定是否修复

本轮找到升级前历史日志中的相同厂商路径冲突：`ac.vmdk`、`ap.vmdk`、`diy.vmdk`、`f1090_fw_b64.vmdk` 与 `msr36_b75.vmdk` 共用 UUID `77626c61-d01b-4def-9e23-f231c9645544`。2026-09-29 日志记录 VirtualBox 6.0.14 并已有这些错误。因此“升级新引入此冲突”的假设被历史证据否定；关闭警告对混合型号的实际影响仍待验证。

1. 只读整理型号 → 厂商镜像路径 → 镜像 UUID → 已登记媒体/差分磁盘父子关系，区分关闭阶段尝试打开所有镜像与实际设备所引用的镜像。
2. 先验证同型号两台设备的清理，再在隔离环境逐个加入混合型号，不一次启动全目录。
3. 若冲突仅发生在无关镜像的关闭扫描，记录其作用域与残留状态，不因此修改原镜像。只有创建、运行或必要回收被真实阻断，才进入修复。
4. 若确需唯一 UUID，另拟独立副本/受支持克隆及引用重建方案：明确 HCL 如何选择副本、父子磁盘依赖与恢复步骤后再执行。禁止修改厂商原镜像 UUID、手改全局 XML 或批量 unregister/delete 原介质。不能把复制文件等同于已解决 UUID 冲突。

通过标准：目标型号能独立创建、运行、停止并退出，媒体和注册状态符合本次清单，原厂镜像哈希不变。此阶段没有通过前，不承诺 AC/AP 或无线支持。

## 5. 后续网络门槛与交付顺序

| 步骤 | 交付物 | 开放下一步的条件 |
| --- | --- | --- |
| A：软件准备 | runtime preflight/manifest、Win32 诊断与 console 租约、严格读写合同、针对性软件测试 | 不依赖真实 guest，可先开发；真实隔离仍不能仅由软件测试判定 |
| B：隔离验收 | 一次生命周期的前后资产差异与回执 | 原历史资产和注册完全保留 |
| C：单设备 CLI | 新设备身份、原始错误/原始字节、命令回显与提示符回执 | 一条只读查询完整且可归因 |
| D：同型号网络 | 两台 MSR36-20 的最小链路、接口/地址回读和双向 ping 丢包统计 | 配置效果与实际连通均独立通过 |
| E：扩展场景 | 三路由器及 OSPF/DHCP 等逐项验收 | 每项配置和协议状态都有 CLI 回读；不是用命令返回代替网络通过 |
| F：混合型号/无线 | 媒体兼容性与目标功能专项回执 | 受影响型号逐项验证，无线另设门槛 |

全过程保留 request_id/operation_id、代码 HEAD、用户与 VM 身份、原始日志、错误码、字节数、完整性标记和哈希。失败回执追加保存，不能覆盖旧负面结果或重放已成功启动来掩盖缺口。

不涉及设备的离线目录、规划和生成能力可继续推进，但只报告离线效果；真实后端虽不需要 guest，仍会触及运行时资产，不能自动视为安全隔离。

本轮只创建此方案文档，没有改产品代码、启动 HCL/guest、变更账号/ACL/镜像、改 BCD/安全设置、再次安装 VirtualBox、提交、push 或发布。系统变更与真实长时验收依后续明确授权和使用者触发执行。

## 6. 本地证据入口

- 交接：`E:/MCP_HCL/HANDOFF.md` §17–18。
- GUI 汇总：`E:/MCP_HCL/docs/plan-b-gui-probe-20261005.json`。
- 控制台负面回执：`E:/MCP_HCL/work/feasibility/plan-b-20261002/gui-attempt-2/boot-console-receipt-2.json`。
- UART/磁盘配置：同目录 `running-topo1-device6.vbox`。
- 清理/媒体日志：同目录 `final-wrapper-log.txt`。
- 升级前同 UUID 错误：`D:/HCL/Log/SimwareWrapperLog/w8p1p-SimwareWrapper.log.2026-09-29.0`（6.0.14 记录与 ac/ap/diy/f1090 的相同冲突）；2026-09-30 日志也有相同冲突。
- 备份回执：`E:/MCP_HCL/work/feasibility/plan-b-20261002/backup-receipt.json`。其 backup_directory 下的 **HCL VMs 子目录**才是 52 个原文件的根。
- 恢复回执指针：同目录 `cleanup-final-pointer.json`；注册恢复为 `registration-restoration-20261005.json`。
- 代码检查对象：dsh-2 的 ConsoleSession、open_console_pipe、HclConsole 和 server 的会话调用关系。

`work/` 仍是本机忽略资产；方案文件不包含厂商镜像或历史回执副本，换机时须另核对这些证据与恢复资产是否存在。
