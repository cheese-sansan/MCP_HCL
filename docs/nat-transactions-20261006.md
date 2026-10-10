# NAT 离散事务：实现稿，测试由 DeepSeek 执行

日期：2026-10-06，用户侧时区 Asia/Tokyo。此次只实现软件、生成参数 Schema 和构建候选 wheel；没有执行单元、模拟、stdio/MCP 调用或真实 guest 测试。旧的 8a46 源码/测试包保持原快照，新改动位于 C:/Users/w8p1p/.codex/worktrees/nat-transactions/MCP_HCL，detached 9963ddc，未提交。

新增 hcl_apply_nat、hcl_remove_nat，外层参数为 project_path、topology、parameters、dry_run=false；parameters 保留固定上游的 router、mode、inside_interface、outside_interface、ACL、内部网络、池名称/地址/掩码和 static_mappings 字段。软件声明面预计48工具/6资源，SDK实际发现与业务行为尚未测试。两个上游行仍 planned，完整61工具/5资源等价没有提升。

## 来源与表达

固定提交 846db381bc2c6ee0229d56e1d7ce8847eb6b213d 的 [请求与流程](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/application/use_cases/apply_nat.py)、[校验规则](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/rules/nat_rules.py)、[注册接口](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/adapters/mcp/tool_registry.py) 均已读取。静态模式提供一对一映射；dynamic 使用池且不复用端口；PAT 可使用外接口地址或池。CLI语法继续沿用本机HCL NAT命令参考与既有 nat-modes-20261006.md。

IOS参数中的 inside_networks 支持 any、host IPv4、任意IPv4 wildcard，并接受现有HCL扩展CIDR。动态/PAT必须提供网络列表；池形式要求有序IPv4范围和连续netmask。每组65536地址是输出预算，不是各固件容量保证；每条成员最多256地址，生成时按数值顺序分段。

IOS编号默认映射：1–99→2001–2099、1300–1999→2100–2799、100–199→3000–3099、2000–2699→3100–3799。acl_namespace=comware 直接引用2000–3999。已有本机数字ACL若没有本事务记录的IOS身份，不以默认映射猜测其归属；调用者可明确使用Comware空间。命名ACL在当前配置中解析类型，未出现时采用basic或显式named_acl_type。

池名到数字address-group的关系记录在按工程/设备/实际VM UUID绑定的本地元数据。新池选择未使用的编号，pool_address_group可显式指定；名称不变时不静默改编号。若当前范围不再匹配记录，仅名称不足以授权修改/删除，需要明确核对原生编号。模拟记录使用独立目录，不能授权原生对象复用。

## 事务和失败

默认写开关在所有I/O之前拒绝。仅选择明确的已阶段化设备，检查模型及当前接口、实际VM/配置盘/串口归属，再进行共享备份与恢复预检。内联ACL更新先回读并保护未请求规则；随后执行NAT差异，比较整个配置视图，最后沿用唯一配置另存、startup指针/内容回读。

已有等价规则/成员不先删后重建；地址分段/合并和ACL格式别名按内容比较。删除时核对实际PAT/NO-PAT模式和池身份，默认清除选中的ACL/池；仍有其他引用则拒绝，可显式remove_acl=false/remove_pool=false保留共享资源。静态使能还服务剩余全局映射时，默认拒绝关闭；disable_static_interface=false显式保留该开关。

operation_key 可重复读取旧回执，键冲突拒绝；回执不完整不会重放命令，也不提升当前验证。timeout_seconds 默认120、最大600，限制每次交换的剩余时间。修改后失败仅新连接恢复原VM UUID及旧startup状态，原失败历史保留。回执/关闭失败返回不完整状态，不以内部错误掩盖可能发生的修改。

## 尚未证明的等价

Comware在外接口及ACL上表达转换条件，没有实现IOS的 ip nat inside 标记；inside_interface目前用于身份/存在性核对。pool_netmask 被校验和记录，但地址组命令只表示范围，未实现或验明IOS池掩码的路由/ARP效果。因此 upstream_behavior_equivalent=false；即使未来原生配置回读通过，也不能直接提升整个上游行或流量/重启等价。

dry_run中的自动池编号只是候选，命名ACL类型可能需运行态解析；预览不连接guest、不写映射，也不证明固件接受这些命令。候选包未安装到实验账号，默认写开关仍关闭。

## 交给 DeepSeek 的必要检查

先固定本稿的源码和候选包SHA，再围绕本次新增面检查三种模式、两种PAT形式、任意wildcard/host/any、编号与命名ACL、幂等键、池范围分段及删除共享引用。对关键失败检查命令/回读/持久化/本地回执失败、超时、恢复目标UUID变化和合成通道假原生标记。测试实现也应核对发现面48与新增Schema；原继承的发现面断言仍是46，需按本次新增面维护。

这些是交接验项，没有在Codex执行。原历史成功与失败继续保留，不以完整旧回归替代新验项；真实生命周期/CLI前提及使用者的具体测试范围仍按测试交接稿执行。测试账号清理条件没有改变。
