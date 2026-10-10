# STP 与端口安全：软件实现稿，待 DeepSeek 测试

2026-10-07，用户侧时区 Asia/Tokyo。独立nat-transactions工作区新增 hcl_apply_stp/hcl_apply_port_security；预计声明面51工具/6资源，SDK发现、协议行为与固件均未测试。旧8a46测试快照未改动，上游对应行仍planned。

外层参数为project_path/topology/parameters/dry_run=false。严格DTO保留上游的switch、PVST模式/VLAN优先级/edge/guard端口以及port/max_mac/violation/sticky/static_macs；另有operation_key和timeout_seconds。priority以JSON自然字符串键表达VLAN，值必须是严格整数及4096倍数；MAC接受标准分组表示并规范化为Comware格式，拒绝非十六进制、重复、全零或组播地址。

## 来源与当前边界

固定上游 [模型](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/models/switch_security.py)、[校验](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/rules/switch_security_rules.py)、[生成器](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/infrastructure/generator/switch_security_cli_generator.py) 已读取。Comware本机参考为D:/HCL/CMD-help/-1069272936/1984907096/351986724.htm及293285528/-1584633467/-1570316705.htm；这些是语法来源，不能代替本型号验收。

H3C的 [PVST实现说明](https://www.h3c.com/en/Support/Resource_Center/EN/Home/Switches/00-Public/Trending/Technology_White_Papers/Spanning_Tree_Technology_White_Paper-6W100/?CHID=509461) 表明其按VLAN使用RSTP。软件将rapid-pvst表达为stp mode pvst，旧IOS pvst算法没有接受映射，整次请求返回unverified。VLAN优先级、原生root primary和edge intent加入；IOS root-primary的动态优先级选择未复现，不把原生root primary等同为同样的优先级策略或实际当选根桥。

本机BPDU保护是全局开关。请求的guard端口必须已为edge或同时明确请求portfast；开启全局保护若会新增影响其他edge端口，则拒绝整次修改。全局mode本身属于请求范围，改变协议模式的转发/收敛效果仍未验明。VLAN压缩区间按编号展开比较，保护未选VLAN及其优先级；显式priority覆盖同VLAN的root-primary请求顺序。

端口安全当前表达已有二层access端口的shutdown/autoLearn、动态或sticky学习属性、静态安全MAC。拒绝自动转换trunk/hybrid/route端口；使能全局安全时若已有dot1x/MAC认证配置可能被重置，也拒绝。已有安全mode、最大数量或sticky转换可能删除未请求学习状态时，不进行隐式迁移。

[H3C端口安全参考](https://www.h3c.com/en/d_201903/1158642_294551_0.htm) 中blockmac带自己的阻塞行为；当前没有IOS protect/restrict的接受映射，这两种请求整体拒绝执行。本机参考max-mac-count上限1024，高于该值需独立型号证据；并非把上游8192上限重新解释为已经支持。静态MAC使用当前access VLAN，未指定时按文档默认VLAN1表达，不新增VLAN或清空其他MAC。

## 事务与证明

默认写门控在I/O前；选中已阶段化的精确设备并绑定实际VM/配置盘/管道后，才备份和恢复预检。完整配置回读核对请求和未请求视图，保存时核对唯一新startup配置及指针。失败只用新连接恢复同一VM UUID，保留失败历史。重复operation_key读取旧记录，不重放命令；过期/不完整状态不提升当前验证。

原生/模拟证明分开，upstream_behavior_equivalent始终false；配置回读不能证明根桥选择、BPDU处理、MAC学习、入侵动作、违规计数/Trap、持久化学习状态或实际流量。全51声明面、这些新增事务及其失败路径本轮都未测试。

## DeepSeek 的必要验项

固定源码和候选SHA后检查严格布尔/整数/JSON键/MAC，默认门控，模式拒绝是否整次无I/O，VLAN范围保护、root/priority冲突顺序、全局BPDU影响与edge冲突、认证重置预防、动态/sticky转换及MAC容量/冲突。检查保存/超时/回读/回执失败和原UUID恢复；相应维护发现面/Schema断言。更广的真实拓扑/流量测试仍按使用者交付的具体范围进行，沿用有效旧结果，不重跑旧成功启动。

上述是待验清单，Codex没有执行。完整61工具/5资源等价、runtime隔离和full_live_gate_passed仍未完成；账号清理保持“全部必要真实测试完成后按创建SID删除，保留profile/VM/回执”的条件授权。
