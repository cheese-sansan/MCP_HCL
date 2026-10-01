# MCP_HCL Codex 交接

当前工作分支：`codex/hcl-live-parity`；版本 0.2.0；更新日期 2026-10-01。
本文件是当前交接入口。DSH 在 `1200f30` 的原交接已保存为 [历史快照](docs/history/dsh-handoff-1200f30.md)，不是当前分支操作指令。

## 目标与权限

维持 61 工具 / 5 资源的 HCL 功能等价目标，区分接口、可观察效果与请求关联证据。
最新使用者授权允许 DSH 快进整合到 Codex，并在 Codex 分支实施 P0/P1；历史“只提交到 dsh”的限制不适用于此次明确授权。
不允许自动 push、PR、发布、重启、BCD 变更、真实设备启动或执行超过一分钟的外部验收。
写开关默认关闭；保护原工程，修改只写副本。原工作区 `E:/MCP_HCL` 及其回执保持原样。

## 分支与验证基线

DSH 固定来源：`1200f30165ebb72a710bd45164231ee12ce6b355`；Codex 原基线：`1005ac3fb455b69b4cbd07b4eaca4f16a3d94e8c`。
7 个 DSH 提交已快进接入，未 squash 或改写历史。Codex 新提交按 P0、目录、规划、生成、MCP/导出、无线修正分组。
当前精确提交、测试与 wheel 哈希以 [验证记录](docs/offline-verification.json) 为准。

- P0 首次全绿：70 项，69 通过 / 1 symlink 权限跳过。
- P0/P1 全套：86 项，85 通过 / 1 symlink 权限跳过。
- 真实 stdio 覆盖 25 工具 / 6 资源、Schema、规划、导出及重载。
- 十类服务有命令模板、未知参数/严格类型拒绝和依赖检查。
- 28 条厂商资料哈希检查通过；不等同固件运行验证。
- wheel 已验证包含必要 JSON 数据，不包含 .vdi/.vmdk/.net/.cfg/.chm。

复现命令见 README；必须运行当前工作区代码。共享解释器仅可用于读取已有依赖，不能将测试悄悄导向 DSH 的 editable 安装。

## 已实现的 P0/P1

P0 原始参数在 SDK 转换前严格校验；未知字段、数字字符串、布尔整数、非有限数及字符串形式 JSON 对象均拒绝。
所有工具返回统一信封，MCP request_id 与 backend_request_id 分开。损坏工程和计划校验是业务 rejected；参数错误是结构化 MCP 工具错误。
阶段与导出支持跨进程持久幂等，同键异输入拒绝，产物哈希变化拒绝；实时命令不自动重放。
后端发送记录只计实际发出的命令。环境脚本读取失败或未知不会通过；需要显式 EntryId 或 verified CreateReceipt，已去掉过期 GUID。

P1 的目录、规划、参数模型、命令模板、操作清单、原子导出和哈希重载都已接入 MCP。
严格输入和字段说明见 [离线 API](docs/offline-api.md)，机器可读 Schema 见 [offline-contracts.json](docs/offline-contracts.json)。

**P1 完整验收仍为 Incomplete**，不能用测试通过或明确不支持代替剩余门槛：

1. AC/AP 的默认 CFG 缺失；目录只有安装端口族和镜像存在证据，不能声称已确认它们的默认 CLI 接口映射。
2. 型号场景端口映射含按安装资料顺序配对的候选，`mapping_verified=false`；需要独立映射证据。
3. 手册确实记载网卡增强（普通最多 7、增强最多 35 连接，S6850 为文档示例），但资料是 5.10.1，5.10.3 逐型号兼容性未验证。
4. 当前规划支持五类 HCL 图模板和 static/OSPF/RIP/none；完整上游规划请求的 WAN、无线客户端等覆盖仍待补齐。
5. 所有配置只验证结构、依赖和有据可查的模板，固件接受、guest 启动和网络连通性仍未验证。

上游工具计数为 12 implemented / 46 planned / 3 unverified；只有窄范围离线合同被标为 implemented。
plan_topology、validate_plan、list_modules 三行保留 planned；总 completion 仍 incomplete。
操作清单是声明式数据，`executable=false`；P2/P3 执行适配器不在本轮实现。

## 代码与证据入口

- `contracts.py`：统一入口、严格原始参数、Schema 和结果信封；SDK 内部适配集中在这里。
- `models.py` / `services.py` / `topology.py`：严格模型、十类服务、跨服务依赖与局部计划验证。
- `catalog.py` / `command_reference.py` / `data/`：安装目录与固定资料哈希；不复制厂商手册正文。
- `planning.py` / `generation.py`：确定性规划、保守修复和离线 Comware 命令模板。
- `artifact_store.py` / `artifacts.py`：SQLite 幂等日志、原子目录提交、哈希清单和重载。
- `offline_tools.py` / `server.py`：25 工具、6 资源；业务逻辑不放进 façade。
- `backend.py` / `console.py`：延续 DSH 的持久连接、帧规则与命名管道客户端，写门控默认关闭。

历史后端协议、帧规则、启动失败与 BCD 操作事实见历史交接 §6、§8、§10–12。
旧回执的可核对索引见 [dsh-receipt-index.json](docs/history/dsh-receipt-index.json)。索引中的路径只在原机器存在。
当前回归与打包日志在本工作区 work/；不提交数据库、生成工程、用户配置或供应商镜像。

## 后续工作

先补齐上面的 P1 证据与请求覆盖，再按既有路线推进 P3 画布 relay、P4 使用者重启后的环境检查、P5 实际 CLI 与连通性、P6 等价收口。
不得把文档里的“一次性引导已武装”当作此刻机器状态；本轮没有重读或修改引导配置。
命名管道与 PuTTY 的并发语义仍未测，create/delete/create_udp 未完全理解的动词仍不可调用。
每次外部成功声明都需要请求关联回执与明确 verified_scope；命令被接受、guest 启动、配置接受和连通性不能互相推断。
