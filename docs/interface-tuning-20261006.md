# 接口调优实现稿：待 DeepSeek 测试

2026-10-06，用户侧时区 Asia/Tokyo。独立软件工作区新增 hcl_apply_interface_tuning；预计声明面49工具/6资源。这里只完成实现、参数Schema与语法解析，未执行单元/模拟/MCP调用或真实测试，旧8a46快照保持不变。上游对应行继续planned。

参数为 project_path、topology、parameters、dry_run=false。parameters 保留上游 router/interface 及 clock_rate、bandwidth、OSPF cost/priority/hello/dead、简单/MD5认证字段和delay；另有operation_key与timeout_seconds。接口名和参数严格类型化，明确选择一个已阶段化设备。

## 来源与支持范围

固定上游 [参数模型](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/models/interface_tuning.py)、[校验规则](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/rules/interface_tuning_rules.py)、[生成器](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/infrastructure/generator/interface_tuning_cli_generator.py) 已读取。Comware OSPF命令和旧固件键长依据本机 D:/HCL/CMD-help/1259698959/867423690/-768537066.htm；bandwidth 参考 [H3C接口命令](https://www.h3c.com/en/Support/Resource_Center/EN/Home/Public/00-Public/Technical_Documents/Reference_Guides/Command_References/H3C_CR-18389/03/202404/2101887_294551_0.htm)。

bandwidth 为期望带宽kbps，不能据此推断实际吞吐。OSPF cost、dr-priority、timer hello/dead 使用对应Comware命令；不改接口地址、管理状态或其他视图。文档约束与IOS不同：当前实现要求同时给定的dead至少为hello四倍；简单密钥最多8个ASCII字符、MD5最多16。并非所有型号/固件的统一能力声明。

clock_rate 没有已验明的本机DCE映射，delay也没有IOS/EIGRP metric的已接受Comware表达。只要请求包含其中任一字段，整个操作在I/O前返回unverified和unsupported_fields；不执行其余子集，不拿link-delay替代。完整上游等价仍缺这些表达。

## 事务与证明层次

默认写门控早于I/O。绑定实际VM/配置盘/管道、完成共享备份/恢复预检后，才下发指定接口命令；随后比较整份配置视图并沿用startup指针和内容回读。配置或保存失败通过新连接恢复原VM UUID，失败历史保留。重复operation_key不重放写入；包含密钥的重用因无法比较已遮蔽凭据而拒绝确认同一请求。

SecretStr用于认证输入；预览、请求回执和返回结果不显示明文，含密钥时历史中的原始base64与相关请求/输出哈希也不对外作为未改写证据。回执/关闭错误保留不完整状态。既有备份仍属于本地私有原始恢复材料；不把它发送到外部或纳入Git/候选包。

认证回读只要求匹配模式、key ID和文档所述密文形状，并保护未请求键/其他命令。它无法证明提供的明文与密文实际相同，因此含认证的结果为partial，authentication_key_verified=false、configuration_verified=false；邻居认证仍需真实证据。标量事务也不证明OSPF邻居、路由收敛或物理性能。

## 必要待验项

由DeepSeek在固定源码/包SHA上检查严格类型与JSONSchema、默认门控、只改指定标量、未请求命令/接口保护、DR priority默认及loopback cost默认、非法计时器与键长、认证模式切换/多key保护、明文/编码历史遮蔽、nonce重用、超时、保存失败与原UUID恢复。未保存的默认hello/dead与密文格式差异不能补写为通过；当前实现对无法匹配的回读拒绝并恢复。

CodeX本轮没有执行这些验项。原发现面测试仍来自46接口基线，需要接手方按新增声明维护；这不是已经通过的49接口验收。full_live_gate_passed=false，完整61/5复现仍Incomplete。
