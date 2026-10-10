# VLAN 名称、PVID 和跨设备事务

日期：2026-10-06，Asia/Singapore。8a46 工作区，detached 9963ddc，修改未提交。

Vlan 增加 names[{vlan,name}]，VlanPort 增加 native_vlan。名称当前支持 1–32 个可打印 ASCII 字符及内部空格，保留大小写；Unicode 控制台编码未验明，不能宣称完整名称字符集等价。trunk 的空 allowed_vlans 表示 all；非空集合按范围压缩，每条最多十个 VLAN 项，多个命令之前只清空一次旧集合。回读比较完整集合、PVID 和名称，接受已知默认 PVID=1、VLAN 1 及范围格式，不能把收到其中一部分当作成功。

新增 hcl_apply_vlan_network(project_path,topology,parameters,dry_run=false)，实际发现面为45工具/6资源。parameters 包含 switch/router、vlans[{vlan_id,name?}]、access_ports[{switch?,port,vlan_id}]、trunks[{switch?,port,allowed_vlans?,native_vlan?,encapsulation?}]、subinterfaces[{router?,parent_port,vlan_id,ip_cidr?,encapsulation?}]。端口行可使用根目标或自己的目标；同一实际设备的别名重复端口会拒绝。只表达 802.1Q；VLANConfig.subnet 元数据和其他封装不在此轮覆盖内。

每个目标必须精确匹配已阶段化设备与 Comware 控制合同；物理接口先对照目录和完整当前配置。未声明的引用只有在当前配置中观察到才可使用，不猜已有 VLAN。新 VLAN 定义分配到本次选中的交换目标；路由器子接口只改变指定 tag/主地址和父接口 shutdown 状态。单设备模型仍要求显式声明 VLAN 依赖，跨设备模型允许核对已有 VLAN。不会重发 sysname 或整份计划。

全部 VM/管道身份核对和全部备份预检完成之后，才修改任何设备；全部运行配置/范围回读通过之后，才开始逐设备持久化。第二台配置或持久化失败时，按逆序在原 UUID 的新连接恢复已经修改设备的运行配置和启动指针。保留失败及每条连接的历史，不重放策略；恢复 UUID 改变或恢复失败分别报告，不能合并成成功。

固定上游 846db381bc2c6ee0229d56e1d7ce8847eb6b213d 的 VLAN 模型、规则和生成器通过连接器读取，其缓存精确 Git blob 分别为 b1dbd18c49233816867da6bd9d11ba52397a8e96、b8e93fe463ec44054cb0a41722fbdbefec5ab245、310485ec47925b6bd8d3cf14a58d93ba7c1b8bb7；记录 work/upstream-verified-20261006/vlan-source-verification.json。apply_vlan.py 同样按该提交读取，用于核对交换机与路由器两条配置和 write memory 路径。

HCL 自带 D:/HCL/CMD-help/-1069272936/1643794375/-40974792.htm 证明名称可以包含内部空格，其 SHA256 为 80140b40b632a1f6cf3137ee2ff7abf646823469f6f67c344623b94f9ad67454。官方 [VLAN 命令参考](https://www.h3c.com/en/Support/Resource_Center/EN/Home/Public/00-Public/Technical_Documents/Reference_Guides/Command_References/H3C_CG-18426/12/202404/2102970_294551_0.htm) 提供 PVID、名称长度和 trunk 语义；[路由器 VLAN 说明](https://www.h3c.com/en/d_202408/2256147_294551_0.htm) 提供 dot1q 子接口依据。语法资料不等于本机固件已经接受这些命令。

只做必要验证：核心兼容13项通过（3.077秒）；新增事务/回读9项通过（3.110秒）；受影响的规划/拓扑/离线/stdio发现25项通过（10.393秒）。没有重跑整个239项历史软件面，也没有真实 guest/网络/启动测试。首次夹具错误留下了 access 与 trunk 双模式，现已修正，失败日志保留在 work/vlan-core-targeted-20261006.txt；各次通过日志另存。

最新 wheel SHA256 c9cbd3be793c9d1dacab6829f7bae40156ef392124060f1f911ae73a1e415f11，44个包文件匹配源码。wheel独立导入、45/6发现面、新映射和默认写拒绝通过。公共准备包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_VlanNetwork 清单已核对，无依赖wheel/厂商资产/密码；旧包保留。当前包 runtime_ready=false。

实际 VLAN 命令/恢复、tagged/untagged 转发、跨 VLAN 路由、重启后的持久化和完整 PT 等价仍未验收；合成通道只能提升 protocol_*。上游仍12 implemented/46 planned/3 unverified，full_live_gate_passed=false。实验账号的自身会话资产清单和 runtime 清理隔离仍待完成；测试结束后停用并按创建 SID 删除账号的授权已记录，不能用软件通过代替真实测试结束。
