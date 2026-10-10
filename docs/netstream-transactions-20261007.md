# NetStream 导出事务：实现稿，待 DeepSeek 测试

2026-10-07，Asia/Tokyo。新增hcl_apply_netstream(project_path, topology, parameters, dry_run=false)，预计声明55工具/6资源。本轮功能/单元/模拟/SDK/原生或流量测试均0。

固定上游 [模型](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/models/netflow.py)、[校验](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/rules/netflow_rules.py)、[接口](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/adapters/mcp/tool_registry.py) 是需求来源。上游操作原生命名Exporter及monitor对象，不能以CLI回读替代isFullyConfigured或对象身份。

本机命令参考D:/HCL/CMD-help/-779967147/-1596426476/-1457440501.htm，SHA256 681e14c3d64bdf144d5249707095a4c3f04398af33ae5b5a314e837802e76892。NetStream的版本/源接口全局共享，每视图文档最多4目的地址，同IP/VPN重配端口覆盖旧值。本稿只操作公共域精确IPv4地址；聚合视图/继承整次拒绝，不猜测作用域。

## 合同与身份

parameters保留device/name/destination_ip/udp_port/version/source_port/monitors/remove，另有interfaces（明确采集接口/方向）、operation_key与timeout_seconds。严格类型/IPv4/端口/版本及重复方向检查加入。monitors为上游命名对象，非空时在I/O前整次unverified，不能转换成接口列表或执行其余子集。

名字仅是按工程/设备/实际VM UUID保存的本地身份，模拟目录不能授权原生复用。全部已有名字须匹配实际目的地址、端口及共享版本/源接口；未知目的地址不被认领。已有名字的空destination_ip沿用原值；新空目的Exporter尚无接受映射，不能伪造创建。空source_port保留当前/记录源接口，不等同每个Exporter独立自动选择。named_exporter_equivalent始终false。

其他目的地址/名字存在时，全局版本/源接口变化整次拒绝。保留AS选项，V5无法保留BGP下一跳时拒绝；版本9/peer-as省略只按本机文档默认归一。全配置及嵌套视图保护加入。明确interfaces只增补指定方向，不清空旧接口，不代表命名monitor等价。

remove=true要求已记录且匹配的名字，只删对应公共域地址，不执行undo全部host，也不清理共享版本/源接口或采集接口。名字漂移、其他名字分享同地址、超过文档目的预算或原生记录来源未验证时拒绝。

## 事务与证明

默认写门控在I/O前，实际VM/配置盘/串口绑定后沿用备份、恢复预检、差异下发、完整回读及startup保存/内容核对。失败仅新连接恢复原VM UUID；名字写入失败且guest恢复完成后恢复原记录，或只移除本次新建的身份文件，不删除目录/VM/账号。重用operation_key只读取历史结果，当前flag=false，不重放命令；不完整状态拒绝自动重试。

dry_run仅返回严格意图，名字解析/移除仍需运行态，预算沿用有界交换。关闭/回执错误不作为完整验收；私有备份/配置材料不进入候选包。配置回读不证明流输出、collector收包、模板刷新、重启、原生命名Exporter/monitor关系或完整上游行为。

## DeepSeek 必要验项

固定源码/候选SHA，检查55声明/Schema、严格类型、monitors整次无I/O、空目的保留/新对象拒绝、名字漂移/模拟记录、共享源接口/版本、同IP端口覆盖、4目的预算、VPN/聚合拒绝、AS/BGP与未请求嵌套配置保护。检查移除精确目标、接口共享、幂等键、预算、保存/元数据/回执失败、原UUID恢复及名字恢复。

这些待验项未由Codex执行。上游行仍planned，12 implemented/46 planned/3 unverified及full_live_gate_passed=false不变，完整61/5复现未完成。沿用有效范围结果、保留失败，不做多余测试。必要真实测试全部结束后按创建SID删除MCPHCLLab并保留profile/VM/证据的要求保持。
