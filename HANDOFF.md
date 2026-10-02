# MCP_HCL Codex 交接

当前工作分支：`codex/hcl-live-parity`；版本 0.4.0；更新日期 2026-10-02。
本文件是当前交接入口。DSH 在 `1200f30` 的原交接已保存为 [历史快照](docs/history/dsh-handoff-1200f30.md)，不是当前分支操作指令。

## 目标与权限

维持 61 工具 / 5 资源的 HCL 功能等价目标，区分接口、可观察效果与请求关联证据。
最新使用者授权允许 DSH 快进整合到 Codex，并在 Codex 分支实施 P0/P1；历史“只提交到 dsh”的限制不适用于此次明确授权。
不允许自动 push、PR、发布、重启、BCD 变更、真实设备启动或执行超过一分钟的外部验收。
写开关默认关闭；保护原工程，修改只写副本。原工作区 `E:/MCP_HCL` 的文件及回执保持原样；按使用者新授权已脱离 dsh，并删除已合入的 dsh 分支。

## 分支与验证基线

DSH 固定来源：`1200f30165ebb72a710bd45164231ee12ce6b355`；Codex 原基线：`1005ac3fb455b69b4cbd07b4eaca4f16a3d94e8c`。
7 个 DSH 提交已快进接入，未 squash 或改写历史。Codex 新提交按 P0、目录、规划、生成、MCP/导出、无线修正分组。
当前精确提交、测试与 wheel 哈希以 [0.4.0 验证记录](docs/progress-verification-040.json) 为准；[0.2.0 记录](docs/offline-verification.json) 保留为历史基线。

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
4. 当前规划支持九类 HCL 图模板和 static/OSPF/RIP/none；完整上游规划请求的 WAN、无线客户端等覆盖仍待补齐。
5. 所有配置只验证结构、依赖和有据可查的模板，固件接受、guest 启动和网络连通性仍未验证。

上游工具计数为 12 implemented / 46 planned / 3 unverified；只有窄范围离线合同被标为 implemented。
plan_topology、validate_plan、list_modules 三行保留 planned；总 completion 仍 incomplete。
操作清单是声明式数据，`executable=false`；0.3.0 已实现工程文件编译器及门控 GUI 打开/保存适配器；实际 GUI/guest 验收未执行。

## 代码与证据入口

- `contracts.py`：统一入口、严格原始参数、Schema 和结果信封；SDK 内部适配集中在这里。
- `models.py` / `services.py` / `topology.py`：严格模型、十类服务、跨服务依赖与局部计划验证。
- `catalog.py` / `command_reference.py` / `data/`：安装目录与固定资料哈希；不复制厂商手册正文。
- `planning.py` / `generation.py`：确定性规划、保守修复和离线 Comware 命令模板。
- `artifact_store.py` / `artifacts.py`：SQLite 幂等日志、原子目录提交、哈希清单和重载。
- `offline_tools.py` / `server.py`：39 工具、6 资源；业务逻辑不放进 façade。
- `backend.py` / `console.py`：延续 DSH 的持久连接、帧规则与命名管道客户端，写门控默认关闭。

历史后端协议、帧规则、启动失败与 BCD 操作事实见历史交接 §6、§8、§10–12。
旧回执的可核对索引见 [dsh-receipt-index.json](docs/history/dsh-receipt-index.json)。索引中的路径只在原机器存在。
当前回归与打包日志在本工作区 work/；不提交数据库、生成工程、用户配置或供应商镜像。

## 后续工作

先补齐上面的 P1 证据与请求覆盖，再按既有路线推进 P3 画布 relay、P4 使用者重启后的环境检查、P5 实际 CLI 与连通性、P6 等价收口。
不得把文档里的“一次性引导已武装”当作此刻机器状态；本轮没有重读或修改引导配置。
命名管道与 PuTTY 的并发语义仍未测，create/delete/create_udp 未完全理解的动词仍不可调用。
每次外部成功声明都需要请求关联回执与明确 verified_scope；命令被接受、guest 启动、配置接受和连通性不能互相推断。

## 2026-10-01 继续推进记录（0.3.0）

使用者明确授权删除无用的 dsh 并继续复现上游。最新上游 HEAD 已读回，仍为固定的 846db381bc2c6ee0229d56e1d7ce8847eb6b213d；未切换到不固定的新基线。

Git branch -d 删除前验证了 dsh 是 Codex HEAD 的祖先，完整 --all bundle 经 bundle verify 通过。E:/MCP_HCL 已 detach 在 1200f30，原文件与历史回执未移除。回执见 docs/history/dsh-branch-retirement.json；bundle 在本工作区忽略的 work/branch-retirement-*/ 下。

新增 project_build.py：验证计划后，从真实 .net 模板克隆型号字段、分配新设备 ID/MAC、生成双向场景连线和注释，再原子提交。模型必须在源工程中存在；port_map 为调用者显式映射，字段须在安装 CLI 默认与源 slot 端口族中存在。映射不因此被标为物理已验证。未知注释引号/反斜杠转义拒绝，普通换行使用观察到的\n编码。

新增 gui_relay.py 与 build_pipeline.py：39 工具 / 6 资源。GUI 接口只能操作带 stage-receipt.json 的输出副本，先核对 SimwareClient PID及完整 HCL - NAME [PATH] 标题；55秒超时后不重放，不引用旧回执。PowerShell 实现打包在 data/hcl_open_gate.ps1，scripts/ 下只保留薄入口，避免两份实现漂移。

100 项回归，99 通过、1 symlink 权限跳过；另有15项最终专项通过。GUI 测试是软件适配器/合成回执测试，不是本机 HCL 窗口验收。当前只读 HypervisorPresent=true；本轮未启动 GUI、Wrapper 或 guest。

阶段 .cfg 保持空占位，CLI 命令放在 MCPArtifacts/commands，防止把交互命令流写成启动配置。完整命令下发、画布拓扑一致性和网络连通性仍待真实回读。相关 full_build/open/save 上游映射继续保持 planned；工具注册数量不等于完成数量。

## 2026-10-02：0.4.0 实现记录

新增 host_settings、subinterfaces、ipv6_ra、wireless_associations，保留 schema_version=1 和旧静态地址字段。地址/动态模式冲突、静态地址落入 DHCP 池、逻辑接口作为物理连线、缺 VLAN/父接口均拒绝。九模板语义已对照固定上游源码；star 的旧 hub-spoke 行为是明确修正。

project_edit.py 同步副本 .net、元数据、绑定计划与生成命令。PersistentConsole 和 PipeLease 提供持续会话、跨请求管道租约、回显/提示符状态机、分页和有限输出。原 Console 接口也使用租约。

deployment.py 从阶段绑定与重新生成的计划读取命令，拒绝被改写的命令文件。原生 save 指定独立备份文件，不改启动配置；more 读完整备份，configuration replace file 验证恢复后才开始正式下发。任一配置错误或读回错误自动恢复所有已修改设备，失败不声明恢复成功。原始输出/配置只放忽略的本地目录。

accept_three_router_lab.py 仅供使用者触发，需要精确项目的 GUI 身份回执、已由使用者启动的 guest、实际拓扑管道名和写开关。验证 OSPF/路由/DHCP/六次 ping，网络验收失败也尝试恢复。full_live_gate_passed 只可能在原生通道和独立 GUI 身份均成立时通过；本轮未执行。

当前硬门槛保持：AC/AP 无本机 CLI 默认资料、无线关联命令缺证据、场景映射未独立验证；原机 HypervisorPresent=true，仍需使用者手动准备环境。第一阶段和第二阶段都没有被软件测试替代收口。

## 2026-10-02：启动配置清理边界

使用者明确批准后，已先导出并读回验证当前 BCD，再移除 MCP_HCL Lab 实验启动项及一次性启动设置。正常 Windows、恢复入口和其他 BCD 对象回读保持不变；未重启验证。备份与回执保留在 `C:/Users/w8p1p/Documents/MCP_HCL-boot-backups/20261002-151945-bd06865eed7a4b7ab8f346c7c518c218/`，备份 SHA256 为 `0514F3230D816A53591C326187EB27E26A423C02BBBAC5C7B3C58E50A2CD0B2F`。

后续复现不再依赖实验启动项，不修改 BCD、系统安全功能或共享 VirtualBox。活动启动项脚本已退役；docs/history 中的原件仅是历史资料，不是操作指令。
