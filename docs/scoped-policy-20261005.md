# 限定范围的 ACL/VLAN 事务

本节记录此前 203 项回归对应的历史包；后续条件扩展和最新 212 项验证见 [ACL 扩展记录](acl-extended-20261005.md)。

日期：2026-10-05，Asia/Singapore。8a46 独立工作区，detached 9963ddc，未提交。完整目标仍为固定上游61工具/5资源。

新增 hcl_apply_acl、hcl_apply_vlan，实际注册面44工具/6资源。严格 parameters Schema 与 dry_run 已实现；默认实时写关闭时早于工程/VM/控制台 I/O 拒绝。命令仅覆盖请求的 numbered ACL 规则/接口方向，或单设备 VLAN/端口/SVI，不重发整份计划。

请求方向可从另一个 ACL 绑定改为本次 ACL，反方向和无关规则保持保护；trunk 允许集合先清空后精确设置。身份验证、原生备份文件比较与恢复预检全部通过后才修改。完整当前配置回读必须包含请求且未改变 sysname、MTU、无关地址/服务等。失败后新连接仅恢复原 VM；UUID 变化或恢复失败报告人工命令与备份，不重放原策略。

完整软件回归203项：202通过、1 Windows symlink 权限跳过，45.239秒。日志 work/scoped-policy-regression-20261005.txt。九项新专项覆盖默认拒绝/预览、范围保持、精确 trunk、不可用备份、中途错误、越界变化、恢复身份变化及恢复失败；真实 stdio 验证 Schema 与门控。

状态化合成 guest 即使标记 native_channel=true，也仅返回 synthetic_policy_transaction_only。protocol_effect_verified/protocol_rollback_verified 不是原生配置或恢复通过。此次没有真实 guest 命令、恢复或网络验收。

wheel SHA256：a55fe8b6b94a8124c312cc10c9e46bd47d71e14882d401ae5bd9f766dc0dfdcf。39个包文件与源码逐字节一致，44/6发现面和默认写拒绝通过。最新公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_Policy 已校验；不含依赖 wheel、厂商或原用户资产，旧包保留。

剩余差距：ACL named 标识、更多端口运算/ICMP type/TCP flags/log/remark 尚未覆盖；VLAN name/native VLAN 与多设备 switch/router 子接口事务未完整实现。MCPHCLLab profile 仍未观察到，先由用户首次登录并验明运行时隔离。上游12 implemented/46 planned/3 unverified不变，full_live_gate_passed=false。
