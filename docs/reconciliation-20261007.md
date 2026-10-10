# 拓扑差异与健康检查：实现稿，测试由 DeepSeek 执行

2026-10-07，Asia/Tokyo。新增 `hcl_diff` 与 `hcl_health_check`，预计声明53工具/6资源。源码位于 `C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL`；8a46旧测试快照及已交接候选包保留。本轮没有执行功能、单元、模拟、MCP发现/调用或真实guest/网络测试。

## 合同与来源

固定上游 [注册接口](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/adapters/mcp/tool_registry.py) 与 [差异/健康逻辑](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/services/topology_diff.py) 是需求来源。上游以原生设备/端口对象提供完整设备名、地址、linked和up。本实现尚无等价的HCL原生设备/线缆清单，工程文件和阶段绑定不能补写成原生事实。

`hcl_diff(project_path, topology, plan, timeout_seconds=120)` 接收已有严格HCL TopologyPlan；`hcl_health_check(project_path, topology, timeout_seconds=120)` 扫描同一阶段工程的已绑定设备。timeout为严格整数1–600。沿用现有总开关：控制台读取也会发送命令并消费独占流，开关关闭时在文件/运行态I/O前拒绝。

目标先做实际用户、运行VM UUID、配置盘和管道归属检查，再逐台发送一次 `display interface`。只使用完整回显、末尾提示符、命令/字节哈希归因的回应。记录逐台观察时间；不是原子拓扑快照。

Windows身份/VirtualBox子进程及CLI交换使用剩余预算；文件读取和控制台构造在有界阶段之间检查截止时间，构造中的已有占用查询上限10秒。故为协作式观察预算，不声明严格全调用墙钟上限。失败不自动重试，不终止其他控制台客户端。

## 结论范围

IPv4区分已观察地址、明确未配置与没有读到字段。冲突或未识别字段拒绝该设备结果。计划使用IPv4主地址比较，辅助地址仍收集供重复地址诊断；IPv6详细回读实现已在后续地址稿加入，格式/型号与行为待验。prefix差异是HCL合同额外诊断，上游原逻辑只比较IP。

差异提供已观察的 `ip_mismatches`、`prefix_mismatches`、未配置/不可观察地址和未观察设备。`staged_missing_devices`、`staged_extra_devices` 仅比较计划与工程声明；工程不可读时为null。原生 `missing_devices`、`extra_devices`、`live_device_count` 为null。新鲜原生回应中的确定地址差异可令 `in_sync=false`；缺完整原生覆盖时不能返回true，模拟依赖也不能得到原生否定结论。

健康记录接口异常和重复IPv4的所有已观察接口。不同路由域可能合法复用地址；后续地址稿只为重复IPv4的拥有接口补读VPN列，缺列仍未知，重复地址不独自证明不健康。linked/peer未知，`down_links`、`cabled_without_ip`、`healthy` 为null。不能以carrier up证明接线，也不能把空闲DOWN口列为断链。L2端口是否需要IP的判断仍须在真实线缆清单可用后实现，不使用阶段链路推断。

`snapshot_complete_for_staged_bindings` 仅表示阶段绑定全部回应成功，不是完整运行拓扑。原生/模拟分开；隔离、连通性、行为等价和full_live_gate_passed不提升。阶段工程/绑定/回执文件扫描期间改变会撤销归因；部分失败保留按设备诊断，回执失败不返回完整审计成功。

## DeepSeek 必要验项

- 固定源码/候选SHA，核对53项声明/SDK发现及Schema。8a46虚拟环境的editable安装指旧源码；使用新源码时明确绑定新src或使用候选隔离环境，避免错误导入。
- 严格参数、关闭门控无I/O、重复名称/不匹配绑定、错误UUID/配置盘/管道、未观察设备、部分失败与中途阶段变化。
- 回显/哈希/提示符；主/辅助地址、明确无IP/字段未知、冲突/未知格式、地址/前缀差异和IPv6未知；UP/DOWN、L2空闲口和重复地址不得得到伪完整健康结论。
- 超时、管道占用、构造/读取/关闭/回执失败、全部目标失败；模拟/原生及阶段完整/全拓扑完整分离。沿用有效旧结果，不重跑无变化的完整历史回归。

真实隔离、CLI和配置/网络验收沿用测试交接的必要范围。两上游行仍planned，12 implemented/46 planned/3 unverified不变。完整61工具/5资源复现仍Incomplete。原生全设备/线缆清单、IPv6路由域及未支持地址格式仍有软件缺口，不能仅靠补测试解决。后续实现/待验项见 [地址观察稿](address-observation-20261007.md)；初始53声明候选保留其原版本边界。
