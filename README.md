# MCP_HCL

与 Agent 客户端无关的 HCL MCP Server。当前在 `codex/hcl-live-parity` 分支开发，版本 **0.4.0**。
目标仍是固定上游 MCP-Packet-Tracer 的 61 工具 / 5 资源在 HCL 上的功能等价；**总体 completion=incomplete**。

接手请读 [HANDOFF.md](HANDOFF.md)，参数与限制见 [离线 API](docs/offline-api.md) 和 [严格契约迁移](docs/contract-v2.md)。

## 当前进度（2026-10-02）

| 项目 | 已验证结果 |
| --- | --- |
| 分支整合 | 保留 DSH 的 7 个提交，快进接入固定 `1200f30`；DSH 工作区未修改 |
| P0 | 原始 JSON 严格校验、统一结果信封、损坏工程业务拒绝、持久离线重试、环境未知值不通过 |
| 注册面 | 39 工具 / 6 资源 |
| P1 软件层 | 九类确定性图模板、规划/估算/解释/保守修复、十类服务参数与配置生成、原子导出及哈希重载 |
| P1 完整验收 | **Incomplete**：AC/AP 默认 CLI 接口映射、逐型号网卡增强兼容性及完整上游规划请求覆盖仍缺证据 |
| 上游映射 | 工具 12 implemented / 46 planned / 3 unverified；资源 5 implemented。implemented 仅在每行 verified_scope 内成立 |
| 本机回归 | 119 项：118 通过、1 项因符号链接权限跳过 |
| 外部效果 | guest 启动、CLI 接受、配置下发、连通性与实时画布验收均未完成 |

## 可调用能力

- 工程与阶段副本：`hcl_list_projects`、`hcl_inspect_project`、`hcl_stage_copy`、`hcl_stage_add_device`、`hcl_stage_link`。
- 发现与目录：`hcl_capabilities`、`hcl_parity_report`、`hcl_list_devices`、`hcl_get_device_details`、`hcl_list_modules`、`hcl_list_templates`。
- 离线规划：`hcl_plan_topology`、`hcl_estimate_plan`、`hcl_validate_plan`、`hcl_explain_plan`、`hcl_fix_plan`。
- 离线产物：`hcl_generate_configs`、`hcl_generate_operations`、`hcl_export_artifacts`、`hcl_load_plan`。
- 后端与控制台：`hcl_bridge_status`、`hcl_backend_capabilities`、`hcl_backend_topology`、`hcl_device_power`、`hcl_console_exec`。

资源：`hcl://capabilities`，以及 `hcl://catalog/` 下的 `devices`、`ports`、`aliases`、`cables`、`templates`。

十类服务为 DHCP、OSPF、RIP、VLAN、ACL、NAT、Security、Wireless、QoS、NetStream，全部有严格参数模型及离线命令模板。
SSH 生成要求设备已有本地主机密钥；SSID、凭据等 CLI token 的字符和长度受 Schema 限制。
无线 AC 配置显式开启射频；FAT AP 模板的射频接口由调用者指定，不推断本机 AP 的默认接口。

`status=staged` 只表示独立工程文件已生成；配置文本只表示模板已生成。
操作清单的实时执行仍标为 `executable=false`；可用 `hcl_stage_plan` 将计划编译到隔离工程。所有运行态验证字段保持 false。

目录中的“网卡增强”是 HCL 手册记载的原生模式，不是 PT 扩展卡，也不是将固定端口冒充模块。
手册版本为 5.10.1；实际 5.10.3 的逐型号兼容性仍未确认。

## 安装与运行

需要 Windows、Python 3.11+、合法安装的 HCL；本次验证使用 Python 3.12、MCP 1.30.0 和 Pydantic 2.13.5。
在**当前工作区**创建独立虚拟环境并安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

若 `python` 或 `py` 不可用，将第一条命令替换为现有解释器的绝对路径；不要修改另一个 Agent 的虚拟环境。

```powershell
$env:MCP_HCL_PROJECT_ROOTS = 'C:\Users\YOUR_NAME\HCL\Projects'
$env:MCP_HCL_OUTPUT_ROOT = (Join-Path (Get-Location) 'work\staged')
$env:MCP_HCL_INSTALL_ROOT = 'D:\HCL'
$env:MCP_HCL_ALLOW_LIVE_WRITE = '0'
.\.venv\Scripts\python.exe -m mcp_hcl.server
```

stdio 服务等待协议输入；将同一命令、环境变量及当前工作区配置到支持 MCP 的客户端。
阶段工具和离线导出可以写独立副本；真实后端改状态动作默认关闭。
只有明确决定操作隔离工程后才设置 `MCP_HCL_ALLOW_LIVE_WRITE=1`。

## 验证与证据

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -X utf8 scripts\verify_offline_reference.py --output work\reference-verification.json
```

骨架测试用合成安装、临时工程和测试管道，不启动 HCL、guest 或改写 BCD。
引用校验只读厂商帮助与手册；它验证资料哈希，不验证固件接受命令。
本次测试与打包摘要见 [0.4.0 验证记录](docs/progress-verification-040.json)；[0.2.0 记录](docs/offline-verification.json) 保留为历史基线。完整日志位于本工作区 `work/`，被 Git 忽略。

DSH 历史说明和交接已原样归档到 [docs/history](docs/history/dsh-handoff-1200f30.md)。
历史回执保留在原工作区，索引只记录原路径和哈希；没有重放失败实验或删除历史证据。

仓库不分发厂商程序、镜像、完整手册或用户配置。上游名称与映射固定在 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d`。
LICENSE：MIT。本轮没有 push、PR、发布、重启、BCD 写入或真实设备启动。

## 0.3.0：工程生成与门控 GUI 接口

`dsh` 已核实全部合入并删除；完整 Git bundle 校验通过。原 E:/MCP_HCL 的文件及历史回执保持原样，工作区停在 detached HEAD。删除回执见 [分支退役记录](docs/history/dsh-branch-retirement.json)。

- `hcl_stage_plan(project_path, stage_name, plan, port_map, idempotency_key?)`：从源工程真实型号模板生成独立 .net、双向链路、注释与新设备绑定。每个连线接口必须显式指定 CLI→场景端口映射，不自动使用未验证的顺序候选。
- `hcl_open_project(project_path, hcl_pid)` / `hcl_save_project(project_path, hcl_pid)`：默认写门控关闭，只接受输出根下带阶段回执的副本。打开只操作打开；保存先核对完整项目名称及路径。每次操作使用新回执目录，超时不自动重放。
- `hcl_full_build(project_path, stage_name, request, port_map, activate=false, hcl_pid?, idempotency_key?)`：串联规划与工程编译。默认仅生成副本；GUI 激活需单独满足写开关、PID和阶段身份条件。实时激活不支持幂等重放。

生成的 CLI 命令保存在 MCPArtifacts/commands/*.txt，DeviceConfig/*.cfg 为新设备空占位文件。命令文本不会被冒充为启动配置或已下发配置。

当前已验证工程文件读回及软件适配器合同，未实际打开 HCL GUI。2026-10-01 本机只读结果为 HypervisorPresent=true，LastBootUpTime=2026-09-30T01:24:52+08:00。Guest、CLI 下发与连通性仍未验证。当前迭代证据见 [progress-verification-030.json](docs/progress-verification-030.json)。

## 0.4.0 当前交付与未完成门槛

离线请求覆盖九种模板，star 已修正为上游的单路由器多交换机定义。新增服务器、显式 WAN、终端类别选择、DHCP 客户端、IPv6 SLAAC/RA、单臂路由子接口及浮动静态路由；custom 保留显式用户计划。

新增阶段编辑：rename_device、move_device、delete_device、unlink、add_note、clear_annotations，均以 hcl_stage_ 前缀注册并写新副本。绑定计划、设备名和双端连接同步；未知绘图字段不删除。

新增 hcl_backup_config、hcl_restore_config、hcl_live_deploy、hcl_verify_connectivity，默认写门控关闭。下发前必须对所有参与设备完成原生备份、备份内容检查与恢复预检；失败时恢复已修改设备，并比较完整运行配置。断连后只为恢复尝试一次新会话，原配置命令不重放。恢复失败返回人工恢复命令。

持久控制台要求命令回显和完整提示符，保存原始字节、处理部分写入/分页，并限制输出和持续流截止时间。每个管道有租约；发现 PuTTY/MultiCC 占用或无法核实占用时拒绝接入。启动配置保存仍是独立操作。

**第一阶段仍 Incomplete**：本机 AC/AP 默认 CLI 配置缺失，无线终端关联命令与独立场景映射没有完整证据。顺序候选不标为 verified，缺资料的无线生成不输出猜测命令。scripts/capture_model_evidence.py 可采集模板与配置的路径、哈希、型号和接口；MCP_HCL_PROFILE_ROOT 可读取带一致源哈希的捕获资料，不能据此推断 factory defaults 或已验证映射。

**第二阶段仍未真实验收**：本轮没有启动设备、改 BCD 或重启。使用者触发步骤见 [live-acceptance.md](docs/live-acceptance.md)。软件回归与模拟恢复不能替代四条 FULL 邻居记录、六份 DHCP 客户端地址及网关和六次双向零丢包 ping。

## 2026-10-02：启动配置清理边界

使用者明确批准后，已先导出并读回验证当前 BCD，再移除 MCP_HCL Lab 实验启动项及一次性启动设置。正常 Windows、恢复入口和其他 BCD 对象回读保持不变；未重启验证。备份与回执保留在 `C:/Users/w8p1p/Documents/MCP_HCL-boot-backups/20261002-151945-bd06865eed7a4b7ab8f346c7c518c218/`，备份 SHA256 为 `0514F3230D816A53591C326187EB27E26A423C02BBBAC5C7B3C58E50A2CD0B2F`。

后续复现不再依赖实验启动项，不修改 BCD、系统安全功能或共享 VirtualBox。活动启动项脚本已退役；docs/history 中的原件仅是历史资料，不是操作指令。
