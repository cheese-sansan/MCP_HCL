# MCP 合同 v2

## 参数与结果

MCP 外层参数使用实际 JSON 对象、数字和布尔值。原始参数先于 SDK 的预解析/类型转换校验；未知键、数字字符串、布尔整数、非有限数值和字符串中的编码 JSON 拒绝。坐标接受 JSON 数字。计划和功能 DTO 由严格模型校验，字段与范围见 [Schema](offline-contracts.json)。

统一结果包含 `contract_version=2`、`status`、`operation_id`、`request_id`、`target`、`verified_scope`、`evidence`、`errors`、`warnings`、`runtime_verified` 和 `full_live_gate_passed`；保留既有业务字段。后端请求 ID 为 `backend_request_id`。外层参数和未知工具是 MCP 工具错误；计划、工程及功能业务拒绝通常返回 `isError=false`、`status=rejected`。状态必须连同证明范围解读。

模拟成功不提升原生验证标志。`staged` 仅表示隔离文件生成，离线预览仅表示意图；`output_received`/`partial` 不等于配置或流量验收。

## 门控、幂等与恢复

- 默认 `MCP_HCL_ALLOW_LIVE_WRITE=0`。原生控制台读取也会发送命令和消费独占流，因此受总开关控制；关闭时先拒绝相关 I/O。
- 阶段工具的 `idempotency_key` 持久化到输出根 `.operations.sqlite3`。同键、同输入和源内容读取已校验产物；不同请求冲突，产物改变拒绝，失败不保留成功键。实时控制不走离线重放路径。
- 配置事务先绑定阶段设备、实际用户、VM UUID、配置盘和管道，再验证备份/恢复入口。核对整个请求与未请求配置范围，保存另存配置并回读 startup 指针和内容。
- 功能事务的 `operation_key` 只读取旧回执，不重新执行命令，也不声明当前状态重查成功。键冲突拒绝；缺失、损坏或非对象记录返回明确未验证结果。含认证密钥的请求无法依据遮蔽内容确认相同输入，因此拒绝确认复用。
- 交换按剩余预算执行；观察预算为协作式检查，不承诺严格墙钟上限。失败恢复使用新连接及原 VM UUID，不重放原修改；恢复身份变化或证据不足保持未验证。
- 回读、保存、元数据、关闭和回执失败必须保留。运行配置、startup、重启与流量结论分别报告，未知字段不补成通过。

## 配置功能边界

| 功能 | 当前支持与明确限制 |
|---|---|
| ACL/VLAN | 编号/命名 ACL、精确规则/绑定删除、VLAN/access/trunk/SVI 和多设备网络事务；保护未请求规则、方向和接口。类型、名称及共享引用须明确匹配，隐式 deny 不覆盖已占用序号。 |
| NAT | static 一对一、dynamic NO-PAT、接口/池 PAT。网络支持 any、host、CIDR、任意 wildcard；IOS ACL 1–99→2001–2099、1300–1999→2100–2799、100–199→3000–3099、2000–2699→3100–3799，Comware 空间可直接指定。既有本机 ACL 不猜 IOS 来源。池名/编号绑定工程、设备、VM；每条成员至多 256 地址，总输出预算 65536。共享 ACL/池/静态开关须显式保留或拒绝删除。inside_interface 目前是引用检查，pool_netmask 是校验/元数据，不证明 IOS ingress-role 或路由/ARP 效果。 |
| 接口调优 | 指定 bandwidth、OSPF cost/priority/hello/dead 和 simple/MD5 认证；同时给定 dead/hello 时至少 4 倍，simple 最多 8 ASCII 字符、MD5 最多 16。clock_rate/EIGRP delay 缺接受映射，整次无 I/O。保护多 key 和其他接口；密文形状只证明模式/key ID，含认证结果保留 partial，明密文对应未验证。预览/历史抑制明文、raw 编码与相关请求/输出哈希，原恢复备份私有保存。 |
| STP/端口安全 | rapid-pvst 的 Comware 表达、指定 VLAN priority/root、edge 和受限全局 BPDU 保护；priority 为 4096 倍数，显式 priority 覆盖同 VLAN root 意图。全局影响其他 edge、认证重置、学习状态破坏和 MAC 冲突拒绝。旧 PVST、protect/restrict、超过当前 1024 容量整次无 I/O。只接受已有二层 access，不能把配置回读解释为根选择、BPDU 或 MAC 学习行为。 |
| NetStream | 公共域精确 IPv4/UDP 目的、共享版本/源接口、明确接口方向和精确删除；文档预算每视图 4 目的。名字是工程/实际 VM 绑定的本地元数据，模拟与原生分目录。已有名字的空目的/源可沿用；未知目的不认领，新空对象、命名 monitors、聚合/继承不执行子集。其他目的存在时拒绝影响共享设置的变化；删除不清空共享接口/版本。不是原生命名 Exporter/monitor 或 collector 收包证明。 |

上述上限来自当前实现及已引用型号/命令资料，不能推广为所有固件的统一能力。

## 观察、安全审计与 GUI

差异/健康观察只扫描阶段绑定设备，核对命令回显、完整原始字节与提示符。IPv4 区分主/辅助、明确无地址与未观察字段；IPv6 按请求/相关设备读取，保留链路本地、DAD、ANYCAST 与生命周期。只有重复 IPv4 才补读 VPN 列；旧列缺失未知，仅接受精确名称和已知 GE 别名，二次 UUID/地址变化撤销归因。阶段扫描中改变也撤销归因。

原生设备/线缆清单、linked/peer 和原子快照未完成，`healthy`、完整库存及正向 `in_sync` 不得伪通过；重复地址不独自证明不健康，IPv6 路由域仍未知。

安全审计要求完整版本/return 和分离的跨行 banner，识别用户/线路凭据，包括 `set authentication password`。simple 可明确分类，cipher/hash 的未知算法不猜强度；RBAC、远程 AAA 和未映射 Cisco 规则保持未知。返回及持久化摘要不含密码、密文、raw 控制台、配置或其哈希；异常使用受限消息，关闭前抑制历史。`secure` 只能 false 或 null，不修复配置，不承诺可靠内存清零。

GUI 打开/保存要求调用者与 SimwareClient/16600 唯一 SimwareWrapper 监听者同 SID/会话且非提权，路径与创建时间/文件哈希匹配。profile/AppData/Temp 符合实际 CIM 目录。打开前拒绝既有 VM 文件、目录或注册（初始 lock.ini 除外）；保存只使用进程内同身份、工程和 stage operation 的许可。控制锁非阻塞，动作端再次复核身份和 collector 哈希，操作后绑定身份；超时不自动重放，错误 caption/工程、缺回执或 validate-only 不证明成功。

注入依赖成功只能证明模拟回执协议；GUI 文件身份仍不证明运行时隔离、实际后端连接、画布库存、guest、配置、连通性或像素等价。不得绕过保护或修改执行策略来制造通过。

## 完整交付边界

固定上游目标为 61 工具/5 资源；当前 SDK 发现 55/6，库存 12 implemented / 46 planned / 3 unverified。完整设备/线缆库存、实时编辑/模块/抓包、若干 IOS 语义、完整安全审计规则、原生命名 NetFlow 对象与安全 Phone 关联仍缺。

`full_live_gate_passed=false`。软件、模拟、VM RUNNING、绿色图标和保存文件不替代真实独占 CLI、配置/startup、隔离、重启与有线/无线流量验收。
