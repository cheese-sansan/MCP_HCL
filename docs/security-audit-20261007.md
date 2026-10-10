# 配置安全审计：软件实现稿，测试由 DeepSeek 执行

2026-10-07，Asia/Tokyo。新增hcl_audit_security(project_path, topology, device='', timeout_seconds=120)，预计声明54工具/6资源。读取实际身份绑定的运行guest配置，不读取计划作为实际安全状态；本轮功能/单元/模拟/SDK/原生测试均0。

## 来源与对应范围

固定上游 [审计规则](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/services/security_audit.py) 和 [桥接读取接口](https://raw.githubusercontent.com/Mats2208/MCP-Packet-Tracer/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/adapters/mcp/tool_registry.py) 为需求来源。上游检查特权凭据、用户凭据、加密开关、MOTD和配置寄存器，仅输出算法分类。

Comware密码命令/类的语义需按固件判断，参考 [MSR Comware 7安全配置](https://www.h3c.com/en/Support/Resource_Center/EN/Home/Routers/00-Public/Configure___Deploy/Configuration_Guides/H3C_MSR_Comware_7_CG-R0615-6W202/12/202202/1553213_294551_0.htm) 及 [H3C RBAC配置示例](https://www.h3c.com/en/Support/Resource_Center/EN/Switches/Catalog/S12500R/S12500R/Technical_Documents/Configure___Deploy/Configuration_Examples/H3C_S12500R_CE_36xx/202409/2277738_294551_0.htm)。cipher不能统一套成Cisco type 7；hash也不根据外观直接证明算法强度。明确simple存储可报告明文，其他模式分别为cipher_algorithm_unknown/hash_algorithm_unknown/unknown。

返回rule_mapping列出原规则对应状态：Cisco enable系列、service password-encryption及config-register旁路没有完整Comware映射，弱哈希分类未验证。不存在super password不能直接判断RBAC不安全。新增Comware诊断仅涉及明确的明文角色/线路凭据、无认证线路和Telnet使能；不下发任何修复配置。

## 读取与凭据边界

沿用默认总开关；关闭时在文件/运行态I/O前拒绝。device可精确指定阶段ID/名称，空值仅扫描阶段绑定中的非PC设备，不声称全原生canvas库存。每个目标核对当前用户、VM UUID/配置盘及管道服务进程，再发送一次display current-configuration；核对回显、原始字节完整性和结尾提示符。timeout严格整数1–600，子进程/交换使用剩余观察预算；既有构造/文件读取是协作式预算，不声明严格全调用墙钟上限。

解析要求完整return结尾和唯一version声明，识别local-user、line/user-interface及全局命令。跨行banner单独隔离，避免将banner里的伪命令当成实际配置。格式未知、冲突或不完整时拒绝该设备观察，不将缺字段默认为安全。

原始配置、密码、密文、raw base64、控制台文本与其哈希均不写入报告/回执。历史在关闭前清除，异常使用固定消息，不回显配置片段；只保存命令名/完成标志的摘要。阶段文件可能含厂商敏感字段，因此其哈希也仅在内存核对，不输出；VM身份按白名单返回。local-user名称/类别/服务类型等标识保留供诊断，存储分类不含凭据值。Python临时不可变字符串不能声明可靠内存清零；此处承诺输出/持久化抑制。

secure最多为false或null：新鲜原生观察中的已知高/中问题可以给负面诊断；未知算法、未映射规则和缺全原生设备覆盖阻止secure=true。没有本地用户只记录缺本地声明，不能据此断言远程AAA或SSH不可用。MOTD没有内容仅为低级提示，不声称法律合规结论。阶段中途变化撤销归因，回执失败撤销已审计证明。模拟观察不提升原生安全结论。

## DeepSeek 必要验项

固定源码/候选SHA，维护54声明及Schema；核对严格参数、默认无I/O门控、阶段选择/PC排除、目标身份、回显/提示符/字节归因、版本/return完整性、跨行banner伪命令、旧/新用户与线路格式、simple字面密码恰好叫hash/cipher时不误分类、hash/cipher未知、RBAC及远程AAA未知、规则排序和secure三值范围。

检查成功、截断、拒绝、超时、部分目标失败和回执/关闭失败时的所有返回/磁盘摘要：不得出现原始密码/密文/控制台内容或配置哈希；检查模拟来源、阶段变化与未观察设备。只做受本次变化影响的必要检查，沿用有效旧结果，保留失败，不重跑无变化完整回归或旧成功guest启动。

上述待验项没有在Codex执行。对应上游行仍planned，12 implemented/46 planned/3 unverified不变；原生库存、完整规则等价与full_live_gate_passed未完成。全部必要真实测试结束后按创建SID/唯一标记删除MCPHCLLab、保留profile/VM/证据的要求继续有效。
