# MCP_HCL 当前交接

当前源码位于 `C:/Users/w8p1p/.codex/worktrees/ddea/MCP_HCL` 的 main，版本 0.5.0，完整交付仍 **Incomplete**，`full_live_gate_passed=false`。使用入口见 [README](README.md)，维护文档见 [docs/README](docs/README.md)。

## 当前版本与证据

当前候选：`C:/Users/Public/Documents/MCP_HCL_Descriptor_20261018_f71b2415/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`bb07a86555255bc6e20a2a5e3a2cd8f3f29cd4ecea2a793ebe9c094910f82586`。59 个包文件与当前源码及候选安装副本逐字节一致。受影响源码检查 52 项全部通过；新候选安装专项 68 项、67 通过、1 符号链接权限跳过。当前 HCL 声明面 55/6，固定上游复现基线 62/5；当前提交的完整 CI 单独核对。旧候选 `2213e9c3…56849f` 保留，它才是本次原生拒绝所用包，不能混作新包的原生结果。

前一候选 `7a74d260…9c9` 及其提交 2f7ec0f 的云端 338 项结果保留；它不包含当前 API 对照增量，不能冒充新源码或候选的结果。当前 CI 状态须按实际提交检查。

旧规范化候选 `2c57afcd…5880a` 和首轮 `b52e247c…56812` 及其结果保留，不能标识修复后的当前源码。

软件证据根：`work/normalization-20261011/ccf9210a95624f7ba9401fbb79e0dead/`，含备份 bundle、来源快照、manifest、SDK/AST 对比和逐项结果。旧候选和原始失败日志保留。

原生证据根：`C:/Users/Public/Documents/MCP_HCL_Native_Test_20261011/c2f6bfc9fcb347d8a5b2f1d2f2fd0556`。原报告记录一次单设备隔离生命周期和 MCPHCLLab 删除；profile/工程/证据保留。旧候选 CLI 被后台 MultiCC 保护拒绝，命令未发送；配置/startup、重启与流量仍未验证。该记录不代表当前现场已重采，也不证明新候选原生通过。

## 下一步

真实 CLI 仍需验证内核独占检查及执行身份，再准备必要专项。用户随后已授权临时普通账号用于最基础测试；2026-10-12 的最小预检在环境隔离检查失败，未启动 HCL/guest 或发送命令。该账号已按本次 SID/创建标记删除，profile 和失败证据保留，原生专项保持 Unverified。有效成功生命周期应复用，不重复启动，不复用已删除账号的旧 SID。真实执行按 [测试指南](docs/live-acceptance.md)；参数、恢复与功能限制见 [合同](docs/contract-v2.md)。

复现目标已扩展并固定到上游 `3c7c7a46b9ea27c914f845d161f95f0fc3f53d5f` 的 62 工具/5 资源，库存为 12 implemented / 47 planned / 3 unverified，HCL 声明面仍为 55/6。原生完整设备/线缆库存、若干 IOS 语义、clock_rate/EIGRP delay、旧 PVST/protect/restrict、原生命名 Exporter/monitor、完整审计规则和安全 Phone 关联等仍缺。

当前源码与历史分支已整合，来源工作区仍保留各自版本；E:/MCP_HCL 的旧 dsh-2 checkout 不是当前 main 源码。远端同步状态以 `git status --short --branch` 和实际 `origin/main` 为准。日期化报告和重复快照已移出仓库维护文档，仍可从 Git、原始证据和仓库外备份追溯。

## 完整复现目标与推进顺序

hcl_parity_report 的 reproduction_targets 保存以下全部目标、依赖和验收条件；不能以接口声明或软件测试把它们标为完成。

| 目标 | 关闭条件 | 当前层次 |
|---|---|---|
| 独占 CLI | 单连接证据、服务器身份/VM/配置盘绑定、真实回显/提示符，忙/未知路径拒绝 | 内核检查已实现；真实 HCL 待验 |
| 完整原生库存 | 全设备、线缆、端口与非 VM 终端的权威清单和稳定归因 | planned |
| 实时编辑/生命周期 | 创建、删除、改名、移动、链接、端口、模块与注释均原生前后回读，统一隔离保护 | planned |
| 有线完整闭环 | 规划→创建/连线→启动→配置→DHCP/OSPF/ping→保存/恢复，无手工复制配置 | CLI/库存前提未满足 |
| 配置行为等价 | NAT ingress/池掩码、clock/delay/EIGRP、STP/BPDU/MAC、认证与原生命名 NetFlow 等语义，以及 native startup/恢复/重启 | partial |
| 安全无线闭环 | AC/AP/交换机/2 Phone，真实 WPA2-PSK、租约、双向 ping、保存/恢复 | blocked |
| 完整实时观察 | 原生 diff/health、端口/VLAN/QoS/IPv4/IPv6/路由域与完整覆盖 | partial |
| 模拟/抓包/工作区 | HCL 可验证的逐事件/逐层等价、截图、项目元数据与工作区设置；普通抓包不替代完整事件合同 | planned |
| 独立 DHCP Server | 明确服务器角色的池读/创建/更新/删除、默认值/范围/DNS/网关、原生回读和实际租约 | planned；不注册占位工具 |
| API 对应 | 62/5 的名称、参数、默认值、错误、结果和能力协商明确对应，不静默缩小范围 | 声明/当前 Schema 对照已实现；转换及行为等价未完成 |
| 交付与证据 | 精确候选的全部必要原生验收、可复现安装与软件/发布检查、分层证据 | blocked |

本轮首先取消 CLI 对任意后台 MultiCC 的一刀切占用结论，改为连接后的内核单实例证据；共享文件锁、原生忙/权限错误、回显、预算、服务器身份与原 UUID 恢复保护保留。多/无限实例和未知信息不发送。Windows 私有合成管道证明软件路径，不证明 VirtualBox/HCL 已接受。

接手只读复核未观察到旧实验账号及运行 Client/Wrapper/MultiCC/guest；本轮不重建账号、不启动 HCL/guest。后续真实 CLI 专项需要已审阅的普通身份/隔离工程。先关闭该前提及原生库存，再推进有线闭环；其余目标继续保留。

本轮源码/测试基线和新回执根：`work/reproduction-62-20261011/018ef18892ed4024a273473dcefef4b6/`。原失败与旧候选不覆盖。

软件交付检查已加入 `.github/workflows/software-ci.yml`：Windows/Python 3.12、默认写开关 0、完整软件检查、wheel 构建及独立日志制品。CI 是软件门槛，不替代原生验收；实际运行状态以对应提交的 Actions 结果为准。

云端干净环境暴露的 Windows 8.3 路径别名误判已修复：证据模板比较解析后的同一文件，路径/哈希/链接保护保留；NetStream 故障注入明确命中规范化目标。首轮失败回执和原工作副本换行字节保存在本轮 work 目录。当前数据文件与 Git/CI 的正式字节对齐，避免旧工作区换行差异混用候选。

## 当前软件增量

2026-10-12 增加 `hcl_parity_report.api_compatibility`，覆盖上游 62/5 固定声明和当前 55/6 MCP 发现结果。逐工具列出参数、必填性、默认值、返回注解、实际 HCL 输入 Schema 和未实现目标；`request`/`parameters` 的同名候选不表示可执行转换。所有输出/错误/行为等价仍为 unverified，自动转换仍 false；上游 `pt_*` 不注册占位别名。API 目标推进到 partial，不提升原生字段或 12/47/3 库存计数。

同时修正库存中“未测试/等待外部测试”的旧描述，明确 NAT、接口、交换机安全、NetStream、观察/审计及 GUI 的软件测试层与原生未验证层。

基线、源码/依赖清单、逐项测试、API 对照快照和新候选身份位于 `work/api-contracts-20261012/5e8578f9bf144f489deb1433ea9733f3/`。旧失败、历史候选及原生证据保留。下一软件目标继续处理配置语义及原生库存的可验证来源；真实调用等待已准备的普通身份/隔离工程。

## 身份预检诊断增量（2026-10-17）

上次最小原生预检记录为 `C:/Users/Public/Documents/MCP_HCL_Basic_20261012/250073e1572e4b0b9491ac125e4a2bb8/result.json`。其中只有 `Profile environment mismatch`，没有具体字段，不能据此断言 TEMP 或其他变量是根因。

现有 `scripts/hcl_lab_environment_identity.ps1` 改为必须显式传入本次预期 SID/profile，不再绑定已删除账号的旧 SID。只读输出 14 个身份/路径检查的 observed、expected、passed/failed/unknown；缺失不猜测，拒绝不符合普通账号身份或 profile/Temp 的路径。即使路径匹配，activation_allowed、runtime_isolation_verified 和 full_live_gate_passed 仍为 false；不修改环境、不创建账号、不启动 HCL。

本机受影响软件检查 14 项全部通过，首次失败保留。另仅在当前原账号执行一次只读观察，14 字段匹配；这不复现或关闭旧临时账号的环境故障。回执根：`work/identity-diagnostics-20261017/bcdea944e8884091967d5f5b3516680d/`。运行器现在把 scripts 的实际字节也纳入测试 manifest。

本轮只修改仓库脚本、测试和文档，包内源码未变，无需重建候选；当前候选 SHA 与 55/6 声明面保持。软件 CI 结果以本轮提交为准，真实 CLI/配置/流量仍未验证。

## 原生最小测试当前结果（2026-10-18）

新账号 MCPHCLQ1018E（SID 尾号 1012）已完成真实 14/14 身份/路径观察，子进程退出码 0。使用逐文件核对的 CPython/标准库和旧候选 2213e9c3…56849f，仅启动一个 MSR36-20，VM UUID 60e8a662-885b-4ccc-b4b3-504aec8037ac。单次探针在 runtime_binding 拒绝，command_outcome=not_sent；未打开控制台或重放，配置/流量未运行。

拒绝的实证原因：HCL 生成的 .vbox 在非身份 ExtraDataItem/DmiBoardSerial 属性中写入字面 0x03，导致标准 XML 1.0 解析失败。原始描述文件 5271 字节，SHA 2708f9dc1e16e94b01f0fbe5598e2cd87a0cac95187d9ac3942a9961e7b3ea21。证据根：`C:/Users/Public/Documents/MCP_HCL_Console_20261018/57ba837b6b0744c5ba181cd6f486e759/`。HCL/guest 已正常停止、保存和退出，账号按本次 SID/marker 停用删除，profile/证据保留。原账号三个记录根共 97 文件无增删或变动；只校验大小/mtime 和不超过 1MiB 文件的哈希。

当前源码仅对已观察到的 Machine/ExtraData/DmiBoardSerial 字面 ETX，在内存身份解析副本中作兼容；不写文件、不改 UUID/镜像/序列号，不删除其他未知控制字节。DTD/实体（含 UTF-16）、注释/CDATA/PI、其他属性与错误视图中的控制字节仍拒绝。原始 descriptor_sha256、UUID/配置盘/管道与真实进程检查保留，验证标志不提升。

首次软件失败、修复、源码 52 项和新安装候选 68 项检查位于 `work/vbox-descriptor-20261018/f71b241523d5469bb713acb767047811/`。捕获文件仅作离线解析复核；新包尚未完成后续真实配置盘/管道/CLI 验证，不得据此关闭 exclusive_cli 或原生总门槛。

历史 C/D 账号的 14 项匹配、独立运行目录、退出码修复及旧 CLI unknown 回执继续保留；D 账号证据根为 `C:/Users/Public/Documents/MCP_HCL_Basic_20261018/df0ea35cc8f2412e8632c7a6847317b7/`，不能把 D 的 unknown 补写成 E 的 not_sent。旧脚本失败不重放，新单次脚本覆盖全阶段回执，回执落盘失败保留已有命令结果。生命周期成功证据继续复用，不另做配置/流量。完整目标仍 Incomplete，full_live_gate_passed=false。
