# Offline API, contract v2

All calls use actual JSON objects/numbers/booleans. The authoritative input
schemas, including every service parameter and range, are in
[offline-contracts.json](offline-contracts.json). Unknown fields are errors.

## Tool inputs and results

| Tool | Arguments | Result payload |
| --- | --- | --- |
| hcl_list_modules | optional model | documented NIC enhancement mode, fixed profiles and compatibility warnings |
| hcl_list_templates | none | nine HCL-native graph templates and source hash |
| hcl_plan_topology | request object | normalized plan, validation, request and source evidence |
| hcl_estimate_plan | same request | device/link/address/route/service counts from the same planner |
| hcl_explain_plan | plan object | deterministic facts and evidence boundaries |
| hcl_fix_plan | plan object | repaired copy, changes and remaining complete topology validation errors |
| hcl_generate_configs | plan object | device-ID → Comware command text, source evidence and warnings |
| hcl_generate_operations | plan object, include_configs=true | versioned create/link/annotation/config intents, executable=false |
| hcl_export_artifacts | plan object, artifact_name, optional idempotency_key | atomic directory, file paths, manifest and hashes |
| hcl_load_plan | artifact_directory | hash-checked normalized plan and source_operation_id |

`artifact_name` is 1–20 ASCII letters/digits/underscores, starting with a letter.
Export/load paths are confined to the configured output root. Occupied names are
not overwritten. Stage tools use the same name grammar and optional durable
idempotency key. Unkeyed calls preserve their original refusal on an occupied name.

## Planning request

Defaults: `schema_version=1`, `name="HCL Lab"`, `template="multi_lan"`,
`routers=2`, `switches_per_router=1`, `pcs_per_lan=0`,
`router_model="MSR36-20"`, `switch_model="S5820V2-54QS-GE"`, `host_model="PC"`,
`lan_pool="10.0.0.0/16"`, `transit_pool="172.16.0.0/16"`,
`routing="static"`, `dhcp=false`.

Templates: single_lan (one router), multi_lan (router chain), star/hub_spoke
(central router), three_router_triangle (exactly three routers). Model choices
must be installed; there is no silent substitution. Port exhaustion, device-limit
overflow, invalid template counts and overlapping/exhausted address pools reject
the request. Static routes use deterministic shortest paths to other LANs.
OSPF and RIP emit explicit service intents. Estimation never invents physical
latency, CPU/memory consumption or firmware support.

WAN/cloud, wireless-client request shapes, EIGRP and the remaining upstream
template semantics are not covered by this request schema. They are not silently
ignored or counted as full planner parity.

Repair changes only exact case aliases, unused physical-interface assignments
and a determinable link medium. It preserves user IPs/routes/services, returns
its changes, and revalidates. Unfixable errors remain rejected.

## Service parameter profiles

Each service is `{device, feature, parameters}`. The feature selects one strict
parameter model; the parameters object cannot be missing or contain a typo.

| Feature | Required core fields / variants |
| --- | --- |
| dhcp | mode, interface; server: pool/network/gateway; relay: servers. Optional DNS and excluded ranges. Server subnet/gateway must match the addressed interface. |
| ospf | process_id, router_id, networks[{network,area}]; optional passive_interfaces. IPv4 networks must contain an addressed interface. |
| rip | classful IPv4 networks; version 1/2 and process_id; optional passive_interfaces |
| vlan | vlans; optional access/trunk ports and svis[{vlan,cidr}] |
| acl | number 2000–3999 or name + acl_type basic/advanced; rules[{id,action,protocol,source,destination,source_port,destination_port,source_port_match,destination_port_match,icmp,tcp_flags,log,remark}]; optional bindings. Addresses accept CIDR/any/host/wildcard. Basic ACLs only match sources. |
| nat | nonempty outbound[{interface,acl}] or static[{interface,global_address,local_address,protocol?,global_port?,local_port?}] |
| security | username/password; privilege 0–15, optional vty_acl/vty_last; Telnet disabled. An existing SSH host key is a precondition. |
| wireless | mode, template, ssid, vlan, psk; AC: AP device/name/model/serial ID and radio; FAT AP: caller-supplied radio_interface |
| qos | classifier/behavior/policy, ACL and/or DSCP match, DSCP remark and/or CIR, bindings |
| netstream | IPv4 collector, UDP port, version 5/9, interfaces with direction |

Referenced ACLs, VLANs, devices and physical interfaces must exist in the plan
and installed catalog. SVI references are permitted when explicitly declared.
Duplicate services/rules/ports, conflicting addresses and unsafe CLI tokens are
rejected. Credentials are caller supplied; there is no default real password.
Exported plans/configs can contain those explicit credentials and stay under the
local ignored output root.

These are bounded profiles, not every option of the named protocols. IPv6 base
interface addresses/static routes are generated; these ten service profiles use
the IPv4 forms listed above. No opaque parameters are saved and silently dropped.

## Evidence and activation

Command reference fingerprints come from the installed HCL command help. The
packed metadata includes syntax names/hashes, not vendor manual contents.
`verify_offline_reference.py` compares 28 source records with the installation.
The HCL 5.10.1 user guide documents native NIC enhancement, but does not prove
5.10.3 per-model compatibility. AC/AP image/family discovery does not supply
their missing default CLI configurations. Port-order pairings are explicitly
unverified candidates.

AC radio activation is explicit in generated configuration, following the local
radio-command reference; H3C's
[Comware 7 wireless examples](https://www.h3c.com/en/Support/Resource_Center/EN/Home/Wireless/00-Public/Doc_Sets/Doc_Packages/H3C_Wireless_All-in-One/03/202209/1689567_294551_0.htm)
also distinguish factory configuration and model/version differences. These
references do not verify this machine's guest state.

Operation manifests preserve devices, links, annotations and optionally config
commands. Scene-port candidates are labeled mapping_verified=false and need the
future execution adapter and mapping/GUI acceptance. All runtime, guest,
configuration and connectivity claims remain false.

## Project compiler and GUI relay (0.3.0)

The four added tools are hcl_stage_plan, hcl_open_project, hcl_save_project and hcl_full_build. See the current Schema snapshot and README for exact arguments. File compilation creates a replacement topology in a copy and retains unrelated source fields. Real source model templates and explicit port_map entries are mandatory. It never derives a live port mapping from catalog order.

Compiled startup files are empty placeholders; generated command transcripts are separate .txt artifacts. The files include a stage receipt binding the copy to its source. GUI activation requires the live-write switch, an existing SimwareClient PID, a staged-copy marker and full caption identity. File receipts are request-local; prior success, preflight-only output or name/path prefixes cannot establish GUI success. No guest boot, CLI deployment or pixel verification is implied.

The full-build tool defaults activate=false and supports durable offline retries. With activate=true it requires hcl_pid and rejects idempotency_key. Optional GUI opening leaves the complete live build partial.

## 0.4.0 additions and migration

All nine template keys are accepted; star now follows the pinned upstream single-router/multi-switch definition. New endpoint categories require explicit documented model selectors. DHCP clients use host_settings and have no static address/default route. IPv6 SLAAC/RA and strict subinterface declarations extend schema_version=1 additively. StaticRoute.preference defaults 60; redundant triangle backups use 254. Custom accepts only an explicit custom_plan.

The six new copy-edit tools are hcl_stage_rename_device, hcl_stage_move_device, hcl_stage_delete_device, hcl_stage_unlink, hcl_stage_add_note and hcl_stage_clear_annotations. Clear removes known NOTE blocks only. Bound-plan edits revalidate/regenerate command artifacts.

Four write-gated staged-device tools are hcl_backup_config, hcl_restore_config, hcl_live_deploy and hcl_verify_connectivity. They resolve IDs through staged bindings. Live deploy re-generates command artifacts from the validated plan to reject altered transcripts, backs up and restore-tests all devices before applying commands, and restores modified devices on failure. Recovery reconnects once only for native restoration; it never replays original commands. Backup restore checks project/topology/device identity and local content hash. Ping parses transmitted/received/loss statistics rather than exit status.

New private captured profiles may be supplied through MCP_HCL_PROFILE_ROOT. Their template/configuration source hashes are rechecked; they do not establish factory defaults, physical mappings or wireless client command syntax. Unsupported wireless association generation remains a hard incomplete gate.

## 0.5.0 原生无线与证据迁移

MCP 注册面保持 39 工具 / 6 资源，contract_version=2，plan schema_version=1。工具外层参数错误为 MCP 工具错误；严格请求模型内部错误保持结构化业务 rejected，不发生类型转换。

TopologyRequest 新增 wireless_clients_per_lan 和 wireless_client_model，明确选择 Phone 时不改变既有 laptop_model / wireless_laptops 的含义。两组无线终端不能重复表达同一组客户端。原生终端必须 DHCP，未验证 IPv6、静态地址、路由和 Comware 服务拒绝。

WirelessSettings 与 Wireless 服务增加 security=open|wpa2_psk，默认 wpa2_psk；psk 只有 PSK 模式才允许且必需。原有携带有效 psk 的请求保持相同意图。WirelessAssociation 也携带相同安全模式，SSID/AP/安全设置必须相互匹配。

Phone 型号同时保留 native_interfaces 和 control_kind=native_gui，default_interfaces 不伪造为 CLI 接口。配置生成只有真实原生设置序列化得到验证后才能成功；目前 wireless_client_commands_unverified / native_terminal_settings_unverified 会阻止完整配置与工程生成。include_configs=false 的操作清单可记录关联意图，但 executable=false，不是完整生成或运行验收。

证据合同独立使用 schema_version=2。MCP_HCL_PROFILE_ROOT 可以读取已导入 artifact/evidence/manifest.json；schema_version=1 的旧单型号资料继续读取，但新增固件内容匹配检查，不接受声明版本与原始配置不符。跨机器推荐 v2，使用 mcp-hcl-lab collect/audit/import；捕获内容、运行成功、独立端口映射和工厂默认分别声明，不能互相推断。

原始配置和原生页面仅存本地私有目录。CLI/MCP 目录摘要只包含型号、来源、哈希、限制及缺项，不返回捕获的凭据或原始配置。

## 2026-10-05：按 LAN 的主机数量与 VLAN 请求

`pcs_per_lan` 和 `laptops_per_lan` 现在接受严格整数或整数数组。每项范围 0–64，数组最多 20 项。整数对所有路由器重复；短数组重复最后一项；空 PC 数组使用 3，空 laptop 数组使用 0；超过实际路由器数量的尾项不创建额外路由器。

例如 `{"routers":3,"pcs_per_lan":[1,2]}` 分配 1、2、2 台 PC。PC/laptop 只接入每个路由器的首个接入交换机；增加 switches_per_router 不再复制这些主机。原生 Phone 的 wireless_clients_per_lan 是另一项 HCL 请求，仍按其无线 LAN 分配且受原生证据门槛限制。

单臂路由 `vlans=0` 使用两组默认 VLAN；非零 PC 数量小于请求 VLAN 组数时按 PC 数量限制组数。VLAN 编号采用 10、20、30…，生成子接口和交换机命令保持一致。现有零 PC 的单臂路由仍可描述预先配置的 VLAN，其完整上游请求验收仍未声明完成。

这是对规划语义的修复：例如 routers=2、switches_per_router=2、pcs_per_lan=3 现在创建 6 台 PC，而不是 12 台。已有显式计划和工程不会自动改写；重新规划请使用新阶段名和新的幂等键，保留旧回执。

Schema 已同步到 hcl_plan_topology、hcl_estimate_plan 与 hcl_full_build；参数描述说明上述分配规则。布尔、字符串、浮点数量不发生整数转换。缺少已安装的主机型号会返回业务 rejected。布局分行适配当前编译器坐标范围；没有像素或实时画布验收声明。

## 2026-10-05：完整拓扑与配置意图校验

hcl_validate_plan 新增 validation_level=topology|configuration，默认 topology。默认除了严格结构、型号/接口、地址与服务依赖外，还要求有效声明的有线链路形成一个连通分量；断开的有线设备返回 topology_disconnected 和组件/孤岛列表。非法端口、自连接或介质错误的链路不用于连接图。

只有使用已知无线接口的关联终端从有线图中排除；用有线接口伪装关联会拒绝。graph.connected 只描述声明的有线图，不验证 VLAN 转发、地址可达性、无线关联或实际流量；所有运行状态字段保持 false。

configuration 允许独立设备的配置意图，返回 graph=null 和 wired_graph_not_checked。配置生成、操作清单和导出重载使用此级别，工程编辑仍可移除链路；规划器、修复器和默认完整校验会指出断开的拓扑。过去只需要逐设备检查的调用者应显式选择 configuration。

OSPF router-id=0.0.0.0 按固定上游意图规则拒绝；空网络列表仍在严格结构层拒绝。SVI 地址统一参与 DHCP/OSPF 依赖解析，服务排列顺序不影响结果，重复接口地址和网络/广播 SVI 地址拒绝。这些是离线意图校验，不代表固件或配置下发通过。

## 2026-10-05：绑定运行设备的查询接口

注册面新增 hcl_inspect_ports、hcl_read_vlans、hcl_read_qos，共 42 工具/6 资源。参数仍以 offline-contracts.json 与实际 tools/list 为准；这三个接口属于受 live-write 开关保护的控制台查询，不是离线计划读取。

| 工具 | 参数 | 返回范围 |
| --- | --- | --- |
| hcl_inspect_ports | project_path、topology，可选 device=''、only_linked=false | 单个/所有已绑定设备的实际接口状态、MAC、IPv4、MTU、速度和双工报告 |
| hcl_read_vlans | project_path、topology、device | 单个设备的详细 VLAN 编号、名称、类型、tagged/untagged 端口 |
| hcl_read_qos | project_path、topology、device | 单个设备的 user-defined classifier、behavior 和 policy 定义及引用 |

device 接受精确 plan ID 或显示名。只有端口查询允许空值表示全部设备。发送 display 命令前核对当前真实用户、注册运行 VM UUID、实际配置文件、已挂载的本工程 ConfigDisk，以及实际命名管道服务进程 PID/owner/startvm UUID；仅 .net/bindings 不足以通过。

端口状态不能证明 HCL 的实时电缆清单，linked/peer 保持 unknown，only_linked=true 明确拒绝；未提供的 PT-specific 字段不能由计划补齐。VLAN 默认/容量也不猜测。未知输出、缺字段、数量不符、归因失败或截断返回 unverified/partial，并保留请求本地原始回执。

注入的模拟通道返回 synthetic_inspection_protocol_only，不能提升 native_readback_verified。实际接口尚未在 HCL guest 上验收，三个上游映射仍 planned，完整 live gate 保持 false。

## 2026-10-05：限定范围的 ACL/VLAN 事务

hcl_apply_acl、hcl_apply_vlan 参数为 project_path、topology、device、parameters、dry_run=false。parameters 严格 Schema 已发布；当前注册面为44工具/6资源。dry_run 只生成命令意图，不连接控制台。非预览先核对运行 VM/挂载配置盘/管道身份，再完成备份、文件比较和恢复预检，才执行请求。

事务只改变请求 ACL 规则/接口方向或 VLAN/端口/SVI，不重发整份计划。trunk 先清空旧集合再精确允许新 VLAN 集合。完整配置回读同时检查意图与越界变化，失败后只用新连接恢复原 VM，不重放原操作。恢复身份变化或恢复失败会保留人工入口。

模拟通道只能提升 protocol_*，不能提升原生 configuration_verified、backup_verified、rollback_verified 或 connectivity_verified。编号/命名 ACL、wildcard 与方向绑定替换已加入，详情见 [命名 ACL 记录](acl-named-20261005.md)。IOS/Comware 未命中动作、持久化与真实验收仍有差距；VLAN name/native VLAN 和多设备 router 子接口也尚未补齐。真实上游行继续 planned。

2026-10-06：implicit_deny 默认 true，以 ACL 内末尾规则编码未命中拒绝。限定事务和共享部署加入唯一配置另存、启动指针/内容比较及失败恢复；模拟通道的 persistence_verified 仍为 false。详见 [持久化与验证边界](acl-persistence-20261006.md)。旧格式验证若显式 implicit_deny=false，只代表 Comware 规则集合检查；真实固件、重启及流量验收仍 pending。

2026-10-06：Vlan.names、VlanPort.native_vlan、trunk all/ranges 和 hcl_apply_vlan_network 已加入，注册面45工具/6资源。跨设备工具按每个实际目标完成身份、备份、范围回读与持久化，失败按原UUID恢复。参数与边界见 [VLAN 事务记录](vlan-network-20261006.md)。已有有效结果沿用，本轮只运行受影响检查，完整真实验收仍 pending。

2026-10-06：hcl_remove_acl 已加入，注册面46工具/6资源。删除编号/命名ACL及可选指定IPv4绑定，保护其他定义/方向/配置，核对保存内容并按原VM恢复；缺少命名类型的离线预览不提升 verified。字段、证据及应用中ACL的未验证边界见 [ACL 删除记录](acl-removal-20261006.md)。

2026-10-06：独立nat-transactions工作区新增hcl_apply_nat/hcl_remove_nat实现稿，预计声明面48工具/6资源；未执行测试或更新已交接8a46快照。外层project_path/topology/parameters/dry_run，严格参数含router、三种模式及ACL/池/映射字段，详细合同和未实现的IOS ingress/netmask等价见 [NAT事务稿](nat-transactions-20261006.md)。两行仍planned，所有新行为等待DeepSeek测试。

2026-10-06：同一软件工作区新增hcl_apply_interface_tuning，预计声明面49工具/6资源。外层project_path/topology/parameters/dry_run；bandwidth/OSPF标量及认证设置见 [接口调优稿](interface-tuning-20261006.md)。串口clock与IOS delay映射未完成，含其一时整次请求不执行；密钥值/邻居认证不提升验证。未执行新增测试，上游行仍planned。

2026-10-07：新增hcl_apply_stp/hcl_apply_port_security，预计声明面51工具/6资源，未执行发现/功能/真实测试。JSON参数和全局/学习状态保护见 [交换安全稿](switch-security-20261007.md)；旧PVST、IOS root算法、protect/restrict及真实行为仍缺，不能从配置或新增接口数量提高全61/5完成率。

2026-10-07：新增hcl_diff/hcl_health_check实现稿，预计声明面53工具/6资源。读取身份绑定的阶段guest接口，报告地址差异、重复地址及不可观察项；缺原生全设备/线缆清单时同步和健康不返回通过。参数、预算和待验项见 [拓扑差异/健康稿](reconciliation-20261007.md)。未执行功能或发现测试，两上游行仍planned。

2026-10-07：53声明不变；差异按IPv6计划加读详细地址，健康新增include_ipv6=false，并仅在重复IPv4时读取VPN实例列。支持格式、DAD/anycast、部分失败和剩余库存缺口见 [地址观察稿](address-observation-20261007.md)。未执行功能/SDK/原生测试，旧候选保持原边界。

2026-10-07：hcl_open_project/hcl_save_project加入SID、非提权令牌、进程/默认监听者绑定、当前账号空运行时前置检查、内存许可与账号共享GUI锁，声明53不变。范围、尚未验证的HCL内部环境/清理边界和必要验项见 [GUI身份稿](gui-identity-20261007.md)。仅语法/构建，未执行采集、GUI或功能测试；旧成功和失败不改写。

2026-10-07：新增hcl_audit_security，预计声明54工具/6资源。只输出身份绑定配置的凭据存储分类/安全诊断，不输出原始值/密文/配置哈希；未知算法和未映射Cisco规则阻止secure=true。合同与必要验项见 [安全审计稿](security-audit-20261007.md)。未执行功能/SDK/原生测试，上游行仍planned。

2026-10-07：新增hcl_apply_netstream，预计声明55工具/6资源，名字身份、目的地址、全局版本/源接口及采集接口限定事务见 [NetStream稿](netstream-transactions-20261007.md)。原生命名Exporter/monitor等价未完成，不把CLI回读替代对象或流量证明。未执行功能/SDK/原生测试。
