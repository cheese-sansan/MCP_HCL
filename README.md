# MCP_HCL

与 Agent 客户端无关的 HCL MCP Server，当前版本 **0.5.0**。本地主分支整合了已有分支历史和最新已验证的软件成果；完整 MCP-Packet-Tracer 61 工具/5 资源等价仍为 **Incomplete**。

接手读 [HANDOFF.md](HANDOFF.md)，完整索引见 [docs/README.md](docs/README.md)。当前发现面为 **55 工具/6 资源**；发现、软件合同、原生配置与真实流量分别记账，`full_live_gate_passed=false`。

## 能力与限制

- 离线工程检查、阶段副本、编辑、严格规划与配置/操作清单生成，支持哈希绑定的导出和重载。
- 原生配置服务包含 ACL/VLAN/NAT、接口调优、STP/端口安全与 NetStream；默认写入关闭，必须绑定实际设备、备份、范围回读和恢复入口。
- 差异、健康、地址观察和安全审计保留未知值及模拟/原生来源；不把缺字段、阶段库存或保存文件解释为完整实时拓扑。
- GUI 保护验证身份、当前账号目录、监听者及工程回执；不能证明厂商运行时环境或清理边界。

上游工具库存仍为 12 implemented / 46 planned / 3 unverified。原生完整设备/线缆库存、若干 IOS→Comware 行为映射、命名 exporter/monitor 与安全 Phone 关联等仍缺。

2026-10-11 具名报告记录一次单设备隔离生命周期和账号清理；候选独占 CLI 被后台 MultiCC 保护拒绝，配置与网络验收未完成。详细事实与范围见 [原生测试记录](docs/native-test-and-cleanup-20261011.md)。

## 安装与运行

需要 Python 3.11+；原生功能需要合法安装的 Windows HCL。使用当前工作区的独立环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
$env:MCP_HCL_PROJECT_ROOTS = 'C:\Users\YOUR_NAME\HCL\Projects'
$env:MCP_HCL_OUTPUT_ROOT = (Join-Path (Get-Location) 'work\staged')
$env:MCP_HCL_INSTALL_ROOT = 'D:\HCL'
$env:MCP_HCL_ALLOW_LIVE_WRITE = '0'
.\.venv\Scripts\python.exe -m mcp_hcl.server
```

stdio 服务等待协议输入；在 MCP 客户端配置相同解释器、工作区和环境。阶段工具仅写隔离输出副本。原生写入须按 [统一测试计划](docs/live-acceptance.md) 处理身份、资产和恢复前提。

## 开发与验证

```powershell
.\.venv\Scripts\python.exe scripts\check_all.py
```

该入口运行 Ruff 和全部软件检查，强制真实写开关为 0，并为每轮保存独立回执。历史成功与失败不覆盖。开发规范和模块职责见 [development.md](docs/development.md)，本轮分支与重构证据见 [normalization-20261011.md](docs/normalization-20261011.md)。

参数见 [离线 API](docs/offline-api.md)、[严格合同 v2](docs/contract-v2.md) 和 [Schema](docs/offline-contracts.json)。旧文档与已退役宿主脚本保存在 `docs/history/`，不作为当前执行入口。
