# MCP_HCL Codex 交接

版本 **0.5.0**；分支 `codex/hcl-live-parity`；更新于 2026-10-02。固定上游 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d`，目标仍为 61 工具 / 5 资源的逐项功能等价。总体 completion=incomplete。

## 权限与来源

DSH 的 7 个提交已快进接入，dsh 分支已安全删除；原工作区 E:/MCP_HCL 保持 detached 1200f30，原工程、回执和依赖不改写。DSH 历史与索引位于 docs/history；0.4.0 的 README/HANDOFF 也已归档。

使用者最新批准的是离线实现及独立实验环境准备。本机不得新增启动项、修改 BCD、关闭安全功能、更换共享 VirtualBox、自动启动 guest 或重启。Push、PR、发布不在范围内；超过一分钟的真实验收由使用者触发。实时写开关默认关闭，工程改动仅写副本。

## 启动配置清理事实

使用者单独批准后，2026-10-02 已先导出当前 BCD 并验证备份，再删除 MCP_HCL Lab 和一次性启动设置。正常 Windows、恢复环境和其他 BCD 对象回读不变；未进行开机验证。备份回执位于 C:/Users/w8p1p/Documents/MCP_HCL-boot-backups/20261002-151945-bd06865eed7a4b7ab8f346c7c518c218/，BCD SHA256 为 0514F3230D816A53591C326187EB27E26A423C02BBBAC5C7B3C58E50A2CD0B2F。

活动 hcl_lab_boot.ps1 和 hcl_lab_environment.ps1 已退役为拒绝执行入口。历史原件仅供审计，不能作为操作指南。环境预检不再依赖启动项名称或 GUID；进程存在、Hypervisor 状态和 guest 列表不能证明原生控制台或网络就绪。

## 已交付的软件

- 严格原始 JSON、统一结果信封、参数/计划错误分类、跨进程离线幂等与产物完整性检查。
- 九模板确定性规划、十类服务模型与有资料依据的离线模板、导出重载、双栈与子接口。
- 隔离工程生成与编辑、双端链路同步、GUI 身份门控；39 工具 / 6 资源。
- 持久控制台、独占租约、完整回显/提示符回读、原生配置备份/恢复预检和部署失败恢复适配器。
- 可搬运的 v2 私有型号证据：相对路径清单、模板身份、配置/版本/接口内容核对、Phone 页面与保存差异、原始来源哈希。导入使用持久幂等，重复冲突、篡改、越界和合成来源均拒绝。
- 显式原生无线终端及安全模式；Phone 不使用 Comware CLI，不允许静态地址、未验证 IPv6 或安全降级。原生字段差异不自动升级为已验证语义。
- mcp-hcl-lab：准备、采集、审计、导入、只读预检及使用者触发的有线验收入口。无线验收入口明确拒绝尚不具备的部署能力。

## 验证与完成门槛

当前软件测试、wheel 和验收包哈希见 docs/progress-verification-050.json。真实 stdio 的 Schema 与目录必须从当前工作区读取；本轮已创建独立 .venv。MCP contract_version=2、plan schema_version=1 不变；型号证据 schema_version=2 是另一种合同。

无线阶段仍 Incomplete：AC/AP 本机默认配置缺失、独立端口/射频映射未验收，Phone 的 WPA2-PSK 关联、设置持久化和恢复未取得真实证据。5.10.1 手册只允许未加密 Phone 无线诊断，不能推断 5.10.3 的安全支持。

实时阶段未执行：当前没有独立实验环境；本机仍保留虚拟化冲突阻塞。软件测试和模拟回执不替代 GUI、guest、配置、恢复、路由、DHCP 或 ping 验收。上游计数仍 12 implemented / 46 planned / 3 unverified，仅在每行窄范围 verified_scope 内成立。

## 下一步

按 docs/live-acceptance.md 在独立环境收集真实 AC/AP/Phone 及有线型号证据。先完成型号/映射资料检查，再运行固定三路由器验收；无线只有真实安全关联、两客户端正确 DHCP 与连通性通过才能收口。不得因导入带有成功标志的文件而提升运行结论。每次运行保留独立新回执，恢复失败逐设备报告，不重放原部署。

## 给下一位 Agent：先做独立软件测试

使用者本次要把项目交给另一个 Agent 测试。先验证现有交付，不把测试请求理解为允许更改宿主机启动、安全、虚拟化设置或开展真实部署。

- 当前工作区：`C:/Users/w8p1p/.codex/worktrees/ed66/MCP_HCL`。交接前 HEAD 为 `2cb7f52`，工作区干净；本次后续提交只更新交接文档。接手先重新检查 branch、HEAD 和 status，不自动切换、重置或清理工作区。
- 被验证的代码提交是 `85bcf24919267a99e7d948a006fa5422de9bdd0e`；`2cb7f52` 添加最终验证记录。现有结果为 **138 项，137 通过、1 项 Windows symlink 权限跳过**，耗时 35.245 秒；46 条资料哈希校验通过，pip check 通过。这些是上一轮结果，本次交接未重跑。
- 原始软件日志：`work/050-final-regression.txt`；隔离 wheel 检查：`work/050-wheel-verification.json` 与 `.log`，复现脚本 `work/verify-wheel-050.py`。它使用合成工程，真实 stdio 指 MCP 传输真实启动，不指真实 HCL guest。
- wheel：`work/wheels-050-final/mcp_hcl-0.5.0-py3-none-any.whl`，SHA256 `f15f123c4f409b44a3ea39b5dce6422d593de13079bf687e28f27d69e815b797`。
- 已准备的搬运目录：`work/lab-bundles/Hcl050/`。内含 wheel、依赖锁定清单、固定实验要求和指南；不含依赖 wheel，独立环境首次安装需要包源访问。所有 work/ 产物和 .venv 都不随 Git 搬运；换工作区后先确认文件存在，缺失时在新目录重新生成，不引用不存在的历史回执作为当前证据。

### 安全的软件测试入口

在当前工作区已有独立 .venv 时执行下面的命令。若在另一工作区测试，改为实际路径并建立自己的环境；不要修改 E:/MCP_HCL/.venv，也不要让它的 editable 安装加载旧 DSH 代码。

```powershell
Set-Location 'C:\Users\w8p1p\.codex\worktrees\ed66\MCP_HCL'
git status --short --branch
git rev-parse HEAD
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + ';' + (Join-Path (Get-Location) 'tests')
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:MCP_HCL_ALLOW_LIVE_WRITE = '0'
# 清除本进程可能继承的私有资料入口，避免回归加载用户资料。
Remove-Item Env:\MCP_HCL_PROFILE_ROOT -ErrorAction SilentlyContinue
$testRun = [Guid]::NewGuid().ToString('N')
$testLog = Join-Path (Get-Location) ('work\agent-test-' + $testRun + '.txt')
.\.venv\Scripts\python.exe -B -X utf8 -c "import mcp_hcl; print(mcp_hcl.__version__, mcp_hcl.__file__)"
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests *> $testLog
$testExit = $LASTEXITCODE
Get-Content -LiteralPath $testLog -Tail 20
if ($testExit -ne 0) { throw "Regression failed; preserve $testLog" }
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B -X utf8 scripts\verify_offline_reference.py `
  --install-root 'D:\HCL' --output ('work\agent-reference-' + $testRun + '.json')
.\.venv\Scripts\mcp-hcl-lab.exe audit `
  --directory work\lab-bundles\Hcl050 --preparation-bundle
```

缺少 D:/HCL 或搬运产物时，仅运行可满足前提的软件检查，并分别报告缺失项。资料哈希不匹配不可改成跳过后宣称资料验收通过。不要为消除 symlink 权限跳过而改变本机系统设置。

### 测试重点与预期拒绝

- 核对真实 stdio 的 39 工具 / 6 资源、`docs/offline-contracts.json` 以及无线请求的 `$defs` 引用。保持外层参数错误与内部请求/计划业务 rejected 的既有分类，验证未知字段和布尔冒充整数没有被转换。
- 独立覆盖九模板、DHCP/静态与 SVI 冲突、子接口、保留 PSK 意图；检查副本编辑后的双端链接、绑定计划及源文件不变。
- 对证据包做搬运、版本/身份不符、路径越界、重复型号、哈希篡改、合成来源及伪造成功标志测试。导入同键并发、跨进程重试和失败写入必须保持来源与旧产物不变。
- 核对原生采集仅发送三条 display 白名单命令；租约、分页、输出归因及不完整失败回执应使用测试通道验证。软件模拟不得提升 native/runtime 结论。
- `accept-wireless` **预期返回 rejected、退出码 2**；Phone 安全关联和设置序列化缺证据导致完整生成拒绝是当前硬门槛。开放计划的结构可通过，不代表配置、工程或安全无线已完整生成。
- 控制台和部署故障测试覆盖备份不可用、中途失败、断连、恢复所有已修改设备、恢复失败及禁止重放。只使用合成设备/管道；不要为了检查恢复行为而在本机调用真实配置命令。

### 真实验收前置条件与交付报告

当前没有独立 HCL 实验环境。最后的只读环境回执 `work/050-environment.json` 记录 Hypervisor=true、VirtualBox 6.0.14、GUI/Wrapper 未运行、running guests 为空；客户端版本资源读不到，状态 unknown。该回执是历史观察，接手需要时可重新只读预检；未知值与进程存在均不能判为 runtime_ready。

真实 GUI 打开、guest 启动、控制台配置和可能超过一分钟的网络验收须由使用者在独立环境明确触发。步骤及固定门槛只引用 [实时验收指南](docs/live-acceptance.md)，不要使用 docs/history 的旧重启或 BCD 指令，也不要自动运行 `accept-wired` 或开启实时写开关。

测试结束报告：被测提交与解释器来源、通过/失败/跳过数、新日志路径、最小复现、源工程/历史产物是否改变，以及未具备条件的真实门槛。保留首次失败证据；若修复，记录修复提交并用新回执复测，不覆盖旧失败。测试通过不能增加 implemented 数量或修改无线/实时 Incomplete 结论，除非有对应层次的真实证据。

### Suggested skills

- `code-review-and-quality`：需要独立检查具体代码差异或调查测试发现时使用。
- `api-and-interface-design`：检查 Schema、错误分类或接口兼容性时使用。
- `handoff`：测试结束后整理新的交接，引用原始回执并保留尚未验证的门槛。


## 2026-10-05：新会话先读 dsh-2 的机器试验问题清单

当前文档的 0.5.0 代码/测试基线不变，**没有合并 dsh-2**。E:/MCP_HCL 现在已在 dsh-2，之前“detached 1200f30”的描述仅属历史。用户另行授权后，共享 VirtualBox 已升级为 6.1.50；已用 Computer Use 在单台 MSR36-20 副本验证创建和 VM 启动进入 guest 系统阶段，CLI/配置/网络仍未通过。

下一会话应读 [E:/MCP_HCL/HANDOFF.md](E:/MCP_HCL/HANDOFF.md) **§17–18** 及 [GUI 实测记录](E:/MCP_HCL/docs/plan-b-gui-probe-20261005.json)。重点问题是：HCL 共享 topo1 运行目录会清理历史文件与 Base 注册；原生管道 PermissionError 原因未定；关闭阶段存在厂商镜像 UUID 冲突警告。旧 COM 缓存错绑已通过定点备份/隔离修正。

试验已停止，原 52 文件和 Base 注册已恢复、原工程哈希保持一致。不要把工程副本当作运行时隔离，不重复成功的单机启动来掩盖控制台缺口，不改 BCD/安全设置或厂商原镜像。新会话先只读分析解决方案，新的真实测试按用户当次指令执行。详细条件、证据路径和排查顺序集中于 dsh-2 交接的问题清单，本处仅作入口指引。

## 2026-10-05：当前独立工作区的控制台修复与账号审阅准备

当前聊天工作区为 `C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL`。已核对原 checkout 干净后，在这个独立工作区复用现有 `9963ddc` 的 0.5.0 基线；HEAD 仍为 detached 9963ddc，以下改动尚未提交。E:/MCP_HCL 的 dsh-2 和 ed66 的 codex/hcl-live-parity 未被合并或改写。完整目标仍为固定上游 61 工具/5 资源；本机保存的上游注册文件哈希与固定清单匹配。

已完成的软件修复：

- 原生 CreateFileW/GetLastError 保留打开失败的 winerror/errno/stage；只对 busy/尚未创建的管道有限等待，访问拒绝不重试。旧 console_unavailable 错误码兼容，细分原因在 detail 中。
- 原生租约使用按用户统一的位置，不同 MCP 输出根仍争用同一管道锁；不终止 PuTTY/MultiCC。该锁不证明外部客户端或不同用户的全局管道安全共享。
- 输出超限不静默截断为成功；部分写入、超时、缺回显、CLI 拒绝均进入不完整历史回执。失败会话必须先归因/重新连接，不能继续发送原请求。MCP、采集和部署结果保留 typed error，恢复重新连接时保留旧连接的失败历史。
- 新 runtime preflight 读取真实 Windows profile/SID、HCL VMs 文件元数据、小型 VM 描述符哈希与 VBox 注册；不启动 HCL，不打开/登记介质，不读大磁盘内容。资产观察和空目录都不提升 runtime_isolation_verified。

验证：原 138 项基线通过（1 权限跳过）；修改后完整回归 **156 项，155 通过、1 权限跳过，41.018 秒**，日志 `work/console-runtime-final-regression-20261005.txt`。随后账号脚本的解析/只读预览/现有账号拒绝三项软件测试全部通过，日志 `work/account-plan-software-tests-20261005.txt`。Create/Disable/Remove 没有执行或实测。

真实 Win32 测试只使用合成管道：busy 回读 231，访问方式不匹配回读 5；没有改变 ACL 或启动 guest。只读宿主预检记录 `work/runtime-preflight-20261005.json`，观察到 VirtualBox 6.1.50、52 个历史文件、一条原 Base 注册，runtime_ready=false。

新私有 wheel 位于 `work/wheels-console-runtime-20261005/mcp_hcl-0.5.0-py3-none-any.whl`，SHA256 `d3e4094d43526992ccde03e74742a6d52f415052f47696757c43537add21d6bf`。wheel 导入、30 个 Python 文件字节核对及 39/6 发现面通过，见 `work/console-runtime-wheel-verification-20261005.json`。独立准备包 `work/lab-account-packets-20261005/MCPHCLLab` 的清单哈希已通过；没有依赖 wheel、没有厂商资产。构建首次遇包源 TLS 失败，改用本机已有的 setuptools wheel 缓存完成，不关闭证书验证。

使用者选择“准备本机专用 Windows 实验账号；先给可审阅创建与回退步骤”。具体步骤见 [账号审阅稿](docs/lab-account-review-20261005.md)，脚本 `scripts/hcl_lab_account.ps1` 默认 Preview。候选 MCPHCLLab 和预计配置目录当前不存在，只生成了计划回执。此请求不等于批准创建账号、真实 HCL 操作或 guest 验收。

下一步先由使用者审阅账号名、标准 Users 权限、密码输入和按创建 SID 回退的步骤。之后如获创建授权，仍不自动启动设备；独立账号的实际 runtime 根、共享端口/管道、厂商镜像引用与清理范围必须验明。当前账号准备不证明隔离通过；CLI/配置/网络/无线仍 Incomplete，12 implemented/46 planned/3 unverified 没有提升，full_live_gate_passed=false。

## 2026-10-05：固定上游主机/VLAN 规划语义已补齐

仍在 8a46 工作区、detached 9963ddc，改动未提交。固定上游请求模型和规划器已通过 GitHub 连接器按精确提交读取；本机 upstream-040 缓存的注册文件经 LF 归一化后与固定清单哈希一致，其原始 CRLF 文件哈希不能直接混用。

PC/laptop 请求现在支持整数和列表，按路由器首个 LAN 分配，短列表补最后一项、空列表默认 3/0；次级交换机不再复制主机。vlans=0 使用默认两组，有 PC 时按 PC 数量限制组数，VLAN IDs 为 10、20…；未知主机型号改为业务拒绝。宽布局分行保持在工程编译器坐标范围。三条相关 MCP Schema 已同步；详情与兼容性说明见 [规划修复](docs/planning-fidelity-20261005.md)。

完整回归 **171 项，170 通过、1 权限跳过，47.943 秒**，日志 work/planning-fidelity-regression-20261005.txt。真实 stdio 的不均匀请求到文件构建链通过，源合成工程保持不变；不代表真实 HCL 创建、DHCP 或网络通过。首个产品错误与测试夹具拒绝的负面回执均保留。

新 wheel SHA256 为 535eedb0499d7181c1d578a5ef8179f9a4245d61eb9602dadafc232b133a64f5，位于 work/wheels-planning-fidelity-20261005/。35 个包文件与源码一致，39/6 发现面和新规划 smoke 通过。最新准备包 work/lab-planning-packets-20261005/MCPHCLLabPlanning 已校验；旧控制台包继续保留，不能当作此轮源码。

完整上游计数仍 12/46/3、completion=incomplete；未创建实验账号、未启动 HCL/guest、未改原 VM/镜像/系统配置。下一步仍须先满足真实隔离与 CLI 门槛；离线验证的连通图与路由语义仍可继续对照上游补齐，不因当前软件回归通过而标记整个目标完成。

## 2026-10-05：完整图校验及授权后的 MCPHCLLab 账号创建

默认 hcl_validate_plan 现在做 topology 级别校验，拒绝断开的有线组件；configuration 级别明确跳过完整图，用于配置意图/导出/文件编辑。无线关联仅按已知无线接口排除，有线接口伪装会拒绝。OSPF 零 router-id 按固定上游合同拒绝，SVI 地址参与 DHCP/OSPF 依赖解析，重复及保留地址拒绝。Schema 已同步，见 [拓扑校验](docs/topology-validation-20261005.md)。

完整软件回归 **183 项，182 通过、1 权限跳过，46.397 秒**，日志 work/topology-graph-regression-20261005.txt。该回归发生在账号密码传递辅助脚本更新之前；后者的三项 Preview/解析测试另行通过，合成密码传输与真实账号 Create 也各自有独立回执。不要把账号动作并入合成软件测试数或 guest 验收。

使用者随后明确指定本机标准账号与测试密码，已授权并完成 MCPHCLLab 创建。独立读取确认 enabled=true、Users=true、Administrators=false；profile_count=0，未自动登录、未加载用户配置或启动 HCL/guest。凭据仅通过同 owner 的 DPAPI 内存管道传入提权助手，未写入 Git、命令行或工作回执。没有修改密码策略。

实际 SID、唯一标记及可用于回退的创建回执见 work/account-creation-20261005/748abd1c1434409d8b9ab95e0f37c68c/，其中 account-receipts/3a42945c83794fcabde4763c5def3e8c/result.json 是未来 Disable/Remove 的依据。详见 [创建记录](docs/account-creation-20261005.md)。账号已存在，不能重复 Create 或按名称猜 SID。

原账号 52 文件的清单/元数据与 VM 描述符哈希、VBox 注册哈希均匹配创建前快照，原工程 hash 仍 CCC821A5…A785570；大磁盘字节没有重新全量哈希。VirtualBox 仍 6.1.50，原 Base 注册 UUID 不变、runningvms 为空。

最新 core wheel SHA256 为 c4d331497d87288b2a0e3af29053d7ccc77165349de8fca18d382768230118ab，35 个包文件与当前源码一致，39/6 发现面和两种校验级别 smoke 通过。准备包复制到 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_Topology，复制后的清单与 wheel 哈希通过；无依赖 wheel、厂商或原用户资产。

下一步需使用者手动首次登录新账号，生成真实 profile，再核对新 SID、VBox 注册与运行时根。新账号创建不等于 HCL runtime 隔离通过；HCL 初始化、guest 和长时网络验收仍由使用者触发。上游计数仍 12/46/3，full_live_gate_passed=false，所有改动未提交、未 push/发布。

## 2026-10-05：42 工具的运行态查询软件面

新增 hcl_inspect_ports、hcl_read_vlans、hcl_read_qos；实际 tools/list 与 Schema 快照为 **42 工具/6 资源**。详见 [查询实现与边界](docs/inspection-20261005.md)。命令前核对实际当前用户、注册 running VM、UUID/CfgFile、本工程 ConfigDisk 挂载与 UART，再核对实际管道服务 PID、owner 及 startvm UUID。SDK/VM 查询只读，默认写开关拒绝早于全部 I/O。

读回要求完整归因和原始哈希；unknown/partial 输出不作空成功。linked/peer 与 linked-only 请求、PT 其余字段、VLAN 默认/容量和完整 QoS 效果仍未验收。模拟 reader 的 native 标志不会提升实际回读结论；每次失败保存新的 transcript/operation_id。

完整软件回归 **194 项，193 通过、1 权限跳过，44.173 秒**，日志 work/inspection-final-regression-20261005.txt。原 39 工具发现面断言造成的首次失败日志保留；两个发现面测试更新为独立的 42 工具期待后通过。真实 Win32 合成管道验证“非 VBox 服务进程拒绝”，没有真实 guest 查询。

wheel SHA256 为 2998eab16d33c62b80fd285109ef44529e025115ad08e698ebeb2216bd2a4b4f，38 个包文件与源码一致。最新公共准备包为 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_Inspection；之前包保留为各自历史快照。账号本轮仍未生成 profile，用户首次登录和真实隔离/reader 验收尚待完成；三个新增上游行仍 planned，计数 12/46/3 未提高，full_live_gate_passed=false。

## 2026-10-05：44工具的 scoped ACL/VLAN 事务

hcl_apply_acl 与 hcl_apply_vlan 已注册，严格 parameters Schema，dry_run=false 默认写门控。见 [事务实现](docs/scoped-policy-20261005.md)。修改限定于请求规则/绑定方向/VLAN/端口/SVI；身份核对、原生备份恢复预检、完整回读与越界保护均必须。恢复只在原 VM 新连接执行，禁止重放原策略。

完整软件回归203项：202通过、1权限跳过，45.239秒，work/scoped-policy-regression-20261005.txt。九项新专项为合成 guest/真实 stdio，不是固件验收。实际发现面44/6，wheel39个包文件匹配源码，SHA256 a55fe8b6b94a8124c312cc10c9e46bd47d71e14882d401ae5bd9f766dc0dfdcf。最新公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_Policy；旧包保留。

更多ACL选项及named标识、VLAN name/native VLAN、router多设备子接口请求仍未覆盖。账号未生成profile，HCL/guest未运行；真实隔离与配置/恢复/网络验收尚未通过。上游12/46/3与full_live_gate_passed=false保持，改动未提交/推送。

## 2026-10-05：ACL 扩展与共享原生目标校验

编号 ACL 新增端口运算/范围、ICMP type/code、TCP flags/established、logging 与 rule comment，严格输入和 Schema 已同步。按配置含义比较已知格式别名；数字协议 0 与 ip 全协议分开。旧同 ID 规则先清除再写，避免旧 flags/comment 残留，其他 ID/名称/配置仍保护。共享部署/备份/恢复/连通性入口统一核对真实当前用户、VM/磁盘/管道身份；恢复固定原 UUID，缺 UUID 的旧原生备份拒绝恢复。

最终回归 **212 项，211 通过、1 Windows symlink 权限跳过，44.838 秒**；work/acl-extended-final-regression-20261005.txt。安装包 40 个文件与源码逐字节一致，wheel 独立导入、44/6 发现面、扩展 Schema 与默认写拒绝通过，SHA256 7e0605be4efd96b6694d14171039619e60ac08cfdd6b63708ef738a18243372f。最新公共准备包 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_ACLExtended 的清单已校验；旧包保留。详见 [ACL 扩展记录](docs/acl-extended-20261005.md) 与验证 JSON。

本轮读回账号 enabled=true、Users=true、Administrators=false、profile_count=0，预计目录不存在；HCL/guest 与 runningvms 为空。创建已完成，不重复 Create；下一步由用户手动首次登录，再验明真实 profile/注册/runtime 根。没有真实 guest ACL/恢复/网络测试；账号不是运行时清理隔离证明。named ACL、完整别名/wildcard 和 VLAN 多设备子接口仍有差距，上游 12/46/3 与 full_live_gate_passed=false 保持。8a46 改动未提交，E:/MCP_HCL 的 dsh-2 未合并、未 push/发布。

## 2026-10-05：命名 ACL 与方向绑定软件实现

编号/命名 ACL、any/host/任意 IPv4 wildcard、上游 ahp/eigrp 与本机 ICMP 名称已纳入严格模型、生成和语义回读。命名身份大小写、编号别名、类型/自动排序/重复头在修改前核对；请求方向的 IPv4 绑定替换，反方向及 ipv6/mac 保留。多 ACL 的清除命令不重复。共享部署/备份/恢复/ping 和备份记录的真实证明位不再由合成通道提升；protocol_* 明确保留软件协议结论。

专项 43 项通过；完整 **227 项，226 通过、1 权限跳过，47.015 秒**，work/acl-named-final-regression-20261005.txt。固定上游三个 ACL 文件经精确 Git blob 核对；首次缓存末尾空行不匹配及 wildcard=0 读回失败回执均保留。见 [命名 ACL 记录](docs/acl-named-20261005.md) 和验证 JSON。

最新 wheel SHA256 5e35a04ff5e286885d7687e53464b7c215fe747a70d56dcfab71f3b8113b5b82；41 个包文件与源码匹配，44/6 发现面、Schema 与默认门控通过。公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_ACLNamed 的清单已校验，旧包保留，无依赖 wheel/厂商/原用户资产。

ACL 尚有 IOS 隐含 deny 与 Comware 未命中默认 permit 的行为差距、持久化/真实流量与 PT object 等价未验明；不得把生成/软件事务当作上游功能全部完成。VLAN 等其余差距继续保留。实验账号 profile_count 仍 0，HCL/guest 与 runningvms 为空；首次登录和真实 runtime 清理隔离仍由用户触发。上游 12/46/3 与 full_live_gate_passed=false 保持，独立工作区改动未提交、dsh-2 未合并、未 push/发布。

## 2026-10-06：ACL 默认拒绝、持久化及测试账号清理要求

本轮为实际进展：默认 implicit_deny=true，在 ACL 内编码末尾拒绝，保留显式 catch-all/无关规则并拒绝无法分配的末尾 ID。限定事务和共享部署另存唯一配置、核对主用 startup 指针/内容及完整运行配置；保护旧 current/main/backup 文件，失败恢复原指针（含 NULL）。replace 询问明确答 N；未核验 guest 备份不会用于恢复。模拟状态只提升 protocol_*，实际固件、重启、流量和全 61/5 等价仍未通过。

必要专项 11 项通过；一次完整回归 **238 项，237 通过、1 权限跳过，72.406 秒**，work/acl-persistence-regression-20261006.txt。其后只读观察发现命名空间访问拒绝被误报空目录，已修复；仅运行相关五项检查（0.050 秒），没有重复完整回归。原错误 observation 和所有旧测试/包保留。详见 [持久化记录](docs/acl-persistence-20261006.md) 及验证 JSON，严格区分两个源码快照的验证范围。

最新公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_ACLPersistenceRuntime，wheel SHA256 335511d9a0b016c1be4c29f3ca2cf4f0d463670f11b4513f03017355fcf5bea0。42 个包文件匹配源码；与完整回归包相比只有 runtime.py 变化，其余 SDK 发现面/Schema/门控结果沿用，44 工具/6 资源不变。

**新事实与下一动作**：MCPHCLLab profile_count=1、LocalPath=C:/Users/MCPHCLLab、Loaded=false，HCL/guest/runningvms 为空。当前调用账号枚举实验目录被拒绝，修正后的 runtime 结果 unknown/WinError 5；不能认为其没有资产。配置目录已生成，不再要求重复首次登录。下一步从实验账号自身会话取得 SID/runtime/注册清单，之后才安排必要的隔离和真实 CLI 验收；没有自动登录、改 ACL、启动 guest 或重跑旧成功启动。

**用户新增直接授权/约束**：此账号只用于测试。必要真实测试结束后按创建回执 SID/唯一标记停用并删除 MCPHCLLab，不重复索取同一清理授权；用户配置目录、VM、回执保留，不扩展成清空用户数据。仅做必要测试，沿用有效结果，避免重复或多余测试。账号清理尚未执行，属于后续交付要求。完整目标 active/incomplete，上游 12/46/3 与 full_live_gate_passed=false；改动未提交、dsh-2 未合并、未 push/发布。

## 2026-10-06：VLAN 45 工具软件面

Vlan.names、trunk PVID/all/ranges 已纳入生成和语义回读；范围批次只清空一次旧集合。新 hcl_apply_vlan_network 支持选中交换端口与路由器子接口的离散事务，所有目标/备份先于修改，所有运行回读先于持久化；第二台设备配置或持久化失败会逆序恢复原 VM 的运行配置与启动指针，错误和恢复身份变化保留。未重发整份计划；模拟原生标记不会提升真实状态。

只做受影响验证：核心兼容13项、事务/回读9项、依赖25项分别通过，日志见 [VLAN 记录](docs/vlan-network-20261006.md) 及验证 JSON。没有重跑整个历史软件面或真实启动，已有有效结果沿用；首个夹具双模式失败回执保留。

实际发现面45工具/6资源；wheel44个包文件匹配源码，SHA256 c9cbd3be793c9d1dacab6829f7bae40156ef392124060f1f911ae73a1e415f11。最新公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_VlanNetwork 已核对，旧包保留。固定上游 VLAN 模型/规则/生成器 Git blob 已核对；ASCII名称、已知范围/default回读和802.1Q为本轮表达范围，Unicode字节合同、subnet元数据及其他封装未覆盖。

真实 VLAN/恢复、tagged/untagged流量、跨VLAN路由、重启持久化和全61/5等价仍未验收，上游12/46/3、full_live_gate_passed=false保持。实验账号自身会话资产清单/隔离仍待完成，账号清理条件未满足；仍遵守测试结束后按SID删除及仅必要测试的直接授权。代码未提交、dsh-2未合并、未push/发布。

## 2026-10-06：实际实验 SID 只读基线及 ACL 删除

用户收到实验账号采集命令后明确授权“由你执行，我正在进行其他工作”。已以隐藏的 MCPHCLLab 子进程执行同一核验内容，没有切换桌面、启动HCL/guest、改ACL或执行策略。实际SID1006/profileC:/Users/MCPHCLLab正确；初始runtime文件0、注册0、进程/错误/阻碍为空。空初始空间不证明厂商生命周期清理隔离，activation_allowed/full_live_gate_passed仍false。

两次失败保留：脚本文件被执行策略拒绝、过长跨凭据命令参数失败。第三次用短命令及子进程内容哈希核对读取同一观察内容，密码仅SecureString输入，没有argv/文件。跨凭据ExitCode未知，成功依据完整SID匹配JSON及errors=[]；PID28884已不存在，profileLoaded=false。完整指针见 [实验采集记录](docs/lab-profile-observation-20261006.md)。原账号52个运行时文件和原Base注册仍存在，不重读大磁盘字节。以后不再说“实验清单因主账号访问拒绝完全未知”，主账号权限仍未改变。

新增hcl_remove_acl，实际46工具/6资源，支持编号/名称解析、可选IPv4解绑、完整定义删除及保存/范围/恢复验证。无关配置与其他方向保护；命名只失去name但留下原number定义不算成功。仅8项必要专项、3项发现/门控依赖通过，没有重跑完整回归或真实删除。说明 [ACL删除记录](docs/acl-removal-20261006.md) 和验证JSON；真实应用引用行为与PT object等价仍planned。

最新公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_ACLRemoval；wheel SHA256 f173376858f8467443fbfe74748b039b8b82bcb0c4bdd82f63741112f72ae62b，45个包文件匹配源码，发现面/门控通过，旧包保留。

下一动作：真实实验账号初始证据已取得，仍须必要的HCL初始化/创建/启动/停止/退出保护范围及CLI门槛，不能据空目录开始批量/长时操作。此次授权范围是只读采集，不扩大为自动guest或系统改变。测试结束按创建SID删除账号、只做必要测试的授权保持有效；账号清理条件未满足。目标active/incomplete，上游12/46/3与full_live_gate_passed=false保持，代码未提交、dsh-2未合并、未push/发布。

## 2026-10-06：后台实验账号 home 环境已核对

没有重复资产清单或整个软件面，只新增进程身份/环境路径观察。发现实际SID正确时，USERPROFILE/APPDATA/TEMP已为实验账号，但HOMEDRIVE/HOMEPATH最初按公共工作目录补齐。执行器现在从该SID的Win32_UserProfile记录取得LocalPath，仅设置子进程WorkingDirectory到真实C:/Users/MCPHCLLab；不修改HOME/USERPROFILE/VBOX_USER_HOME或用户环境。

同一SID复核后USERPROFILE及home组合都指向实验profile；执行策略保持Restricted，HOME/VBOX_USER_HOME为空，其他路径无原账号引用。TEMP/TMP保留观察到的8.3短名，不据此推断HCL的实际运行目录。PID39184结束、profileLoaded=false，HCL/guest未启动。原公共工作目录回执05b0bf67fae3435ba13bfd1e5399a976和修正回执51eb214743044755ab5e05f492df4c17都保留，汇总work/lab-environment-verification-20261006.json。

说明 [实验环境边界](docs/lab-environment-20261006.md)。真实初始0文件/0注册基线沿用；HCL生命周期清理范围和CLI/网络仍未验明，activation_allowed/full_live_gate_passed=false。此更新只涉及执行器/文档，不重建应用wheel、不重复既有测试。46工具/6资源与12/46/3不变，账号清理仍待必要真实测试结束，目标active/incomplete。


## 2026-10-06：NAT 模式软件面与生命周期启动前记录

计划模型/生成新增地址池 PAT/no-pat、命名 ACL 引用、地址成员分段及组视图区分；只运行17项相关检查与2项stdio/Schema依赖，均通过，没有重跑全套。详见 docs/nat-modes-20261006.md 和验证JSON。最新公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_NatModes，wheel SHA256 65bc0c3b41bdabbddd5c1cdcd0782f17621f5de73d6b9f78dbe5907895e1ff41；45个包文件匹配、46工具/6资源。离散NAT应用/删除及真实流量仍未完成，上游12/46/3不变。

用户先延期，后明确空闲并允许接管本次单设备生命周期。原52文件完整字节与备份一致，原工程/注册及相关厂商盘保护清单已记录。本次尚未启动HCL/guest：第一步跨账号环境继承失败、第二步审阅副本访问拒绝均保留；改用Windows PowerShell5.1及新写入的同字节可读输入后，真实SID和路径通过，工程副本已准备。观察启动器现在提前拒绝PowerShell7；不手动覆盖环境或改原ACL。

第三操作 f37f1f638a9f419ea395225670f42951 启动H3C Cloud Lab.exe出现UAC，当前等待用户手动取消；manifest确认启动器requireAdministrator，客户端/Wrapper为asInvoker，正常权限入口仍待确认。不得自动处理认证提示或输入管理员凭据，不能据此运行在原账号。记录 docs/isolation-trial-execution-20261006.md。runtime隔离/CLI/网络门槛未通过，账号清理条件未满足；测试结束按SID删除和仅必要测试的授权保持，代码未提交/未push，目标active/incomplete。


## 2026-10-06：测试交由 DeepSeekHarness 下的 DeepSeek

使用者明确将测试交给 DeepSeekHarness 下的 DeepSeek。Codex 已停止测试；未打开审阅工程、创建设备或启动 guest。单设备生命周期、CLI/配置/网络及完整上游等价仍未通过，full_live_gate_passed=false。

交接稿：C:\Users\w8p1p\AppData\Local\Temp\MCP_HCL_DeepSeek_Test_Handoff_20261006_ccf4b7d7.md。当前收尾时无 HCL/guest/采集进程，实验 profile 未加载；原52文件元数据/描述符及注册哈希与恢复后一致。控制器与观察器期限失败保留。最新事实见独立工作区 docs/isolation-trial-execution-20261006.md；必要测试结束后按创建 SID 停用并删除账号、保留 profile/VM/证据的条件授权继续有效，账号暂留供接手测试。
