# 有线拓扑与服务依赖校验

日期：2026-10-05，Asia/Singapore。基于固定上游 846db381bc2c6ee0229d56e1d7ce8847eb6b213d 的 [拓扑规则](https://github.com/Mats2208/MCP-Packet-Tracer/blob/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/rules/topology_rules.py)。当前改动在 8a46 独立工作区，HEAD 为 detached 9963ddc，尚未提交。

## 当前行为

hcl_validate_plan 默认完整 topology 校验：有效的声明有线链路必须形成一个连通分量。错误端口、自连接、重复占用及介质不符的链路不用于建立连通关系。断开时返回 topology_disconnected、稳定排列的组件与孤岛列表。

已知无线接口上的关联终端按无线意图处理，不误判为有线孤岛；用以太网接口伪装无线终端拒绝。无线安全和关联门槛独立保留。

validation_level=configuration 用于逐设备配置意图：保持接口、地址及服务语义检查，允许设备之间暂未连线，并明确返回 graph=null 与 wired_graph_not_checked。配置生成、操作清单、导出重载及文件编辑沿用这一用途；完整规划及默认校验不会把孤岛报告为有效整体。

OSPF router-id=0.0.0.0 按固定上游规则拒绝，空 network 列表由严格结构模型拒绝。该合同不声称在本机固件上尝试过这些命令。SVI 声明预先加入地址表，DHCP gateway/interface 和 OSPF network 不再因地址写在 VLAN 服务内而被错误拒绝；服务顺序不影响解析。重复 SVI 地址/接口以及 IPv4 网络、广播地址拒绝。

graph.connected 不等于网络连通，不检查 VLAN 转发、下一跳实际可达性或协议邻接；runtime/guest/configuration/connectivity/full_live_gate 都保持 false。

## 验证

完整回归 **183 项，182 通过、1 Windows symlink 权限跳过，46.397 秒**。日志 work/topology-graph-regression-20261005.txt。

新专项覆盖断开的组件、非法连接、单设备、无线排除、伪装关联、配置级别的导出重载、OSPF 拒绝、SVI 依赖/冲突及实际 MCP stdio 的默认级别和严格参数。原文件编辑移除链路的能力保留。

首份 SVI 测试在严格结构层已被拒绝，未进入服务依赖层；原失败日志 work/topology-graph-service-tests-20261005.txt 保留。后续另用结构合法的跨地址声明冲突验证依赖解析，新日志 work/topology-graph-service-tests-cross-declaration-20261005.txt。

新 wheel：work/wheels-topology-validation-20261005/mcp_hcl-0.5.0-py3-none-any.whl。SHA256：c4d331497d87288b2a0e3af29053d7ccc77165349de8fca18d382768230118ab。35 个包文件与源码逐字节一致，39 工具/6 资源发现面、断开拓扑拒绝与配置级别接受均通过。回执见 work/topology-validation-wheel-verification-20261005.json。

最新准备包 work/lab-topology-packets-20261005/MCPHCLLabTopology 已校验，并复制到 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_Topology；复制后的清单与 wheel 哈希再次通过。没有依赖 wheel、厂商程序、镜像或用户配置。旧包作为历史源快照保留。

## 后续状态

使用者明确指定本机 MCPHCLLab 账号与密码后，标准账号已实际创建并独立核对，详见 [账号创建记录](account-creation-20261005.md)。没有自动登录或启动 HCL/guest。

完整复现仍 Incomplete；上游计数 12 implemented / 46 planned / 3 unverified 没有提高。真实运行时隔离、CLI、配置、网络和无线门槛尚未通过。
