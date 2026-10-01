# MCP_HCL

与 Agent 客户端无关的 HCL MCP Server。当前在 `codex/hcl-live-parity` 分支开发，版本 **0.2.0**。
目标仍是固定上游 MCP-Packet-Tracer 的 61 工具 / 5 资源在 HCL 上的功能等价；**总体 completion=incomplete**。

接手请读 [HANDOFF.md](HANDOFF.md)，参数与限制见 [离线 API](docs/offline-api.md) 和 [严格契约迁移](docs/contract-v2.md)。

## 当前进度（2026-10-01）

| 项目 | 已验证结果 |
| --- | --- |
| 分支整合 | 保留 DSH 的 7 个提交，快进接入固定 `1200f30`；DSH 工作区未修改 |
| P0 | 原始 JSON 严格校验、统一结果信封、损坏工程业务拒绝、持久离线重试、环境未知值不通过 |
| 注册面 | 25 工具 / 6 资源 |
| P1 软件层 | 五类确定性图模板、规划/估算/解释/保守修复、十类服务参数与配置生成、原子导出及哈希重载 |
| P1 完整验收 | **Incomplete**：AC/AP 默认 CLI 接口映射、逐型号网卡增强兼容性及完整上游规划请求覆盖仍缺证据 |
| 上游映射 | 工具 12 implemented / 46 planned / 3 unverified；资源 5 implemented。implemented 仅在每行 verified_scope 内成立 |
| 本机回归 | 86 项：85 通过、1 项因符号链接权限跳过 |
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
操作清单明确 `executable=false`，不能直接作为实时部署器使用。所有运行态验证字段保持 false。

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
本次测试与打包摘要见 [验证记录](docs/offline-verification.json)。完整日志位于本工作区 `work/`，被 Git 忽略。

DSH 历史说明和交接已原样归档到 [docs/history](docs/history/dsh-handoff-1200f30.md)。
历史回执保留在原工作区，索引只记录原路径和哈希；没有重放失败实验或删除历史证据。

仓库不分发厂商程序、镜像、完整手册或用户配置。上游名称与映射固定在 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d`。
LICENSE：MIT。本轮没有 push、PR、发布、重启、BCD 写入或真实设备启动。
