# ACL 条件与原生身份校验

此记录对应历史 212 项回归；命名/wildcard/绑定及最新 227 项验证见 [后续记录](acl-named-20261005.md)。

日期：2026-10-05，Asia/Singapore。8a46 工作区，detached 9963ddc，改动未提交。此记录接续 [限定事务](scoped-policy-20261005.md)，不改写旧测试或安装包。

编号 ACL 已加入端口 eq/neq/gt/lt/range、ICMP type/code、TCP 正向 flags/established、logging 和 rule comment。整数范围、运算参数数目、协议关系和互斥条件由严格 Schema 检查；原整数端口字段保留。备注目前只接受 1–127 个可打印 ASCII 字符。厂商本机帮助页 D:/HCL/CMD-help/-1231731996/-1314442724/911448879.htm 的 SHA256 为 92d0650ba638733c090f6657494577ea703adc75d811c95f46b4adcc14ee6c56，提供这些语法的离线依据；未复制厂商文档到仓库。

配置回读按规则含义比较：允许已知协议、端口和 ICMP 别名、条件顺序差异以及省略 any。未知条件仍拒绝；ICMP 未指定 code 不等于 echo 的 code=0，数字协议 0 不等于 ip（全部 IP 协议）。已有同 ID 规则先 undo 再写，以清除旧 flags/log/comment；其他 ID、ACL name 和未请求配置保持保护。

共享部署、备份、恢复和连通性入口现在与限定事务一样，在控制台操作前核对当前用户、running VM、UUID、配置文件、工程磁盘与管道服务身份。恢复再次核对原 VM UUID；旧原生备份缺少该 UUID 时拒绝恢复。这里保护实际操作目标，不代表 HCL 初始化/退出的清理边界已经隔离。

最终软件回归 212 项，211 通过、1 Windows symlink 权限跳过，44.838 秒；日志 work/acl-extended-final-regression-20261005.txt。新增九项测试覆盖条件生成、严格输入、格式别名、条件差异、数字协议 0、旧条件清除及原生目标/恢复拒绝。先前 211 项结果和首次构建保留在各自目录。

最新 wheel SHA256：7e0605be4efd96b6694d14171039619e60ac08cfdd6b63708ef738a18243372f。40 个包文件与源码逐字节一致；从 wheel 独立导入后，44 工具/6 资源、扩展 Schema、协议 0 反例及默认 writes_disabled 门控通过。公共准备包为 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_ACLExtended，复制后清单和 wheel 哈希通过；不含依赖 wheel、凭据、厂商程序/镜像或原用户资产。

本轮独立读回确认 MCPHCLLab 已启用、Users=true、Administrators=false、profile_count=0，尚无实际用户目录；HCL/guest 进程与 runningvms 为空。账号已创建，不重复 Create。用户需手动首次登录，然后核对 profile、注册及真实运行时根。

此次没有真实 guest ACL 命令、恢复或流量验证。合成事务仅证明软件合同；native configuration/recovery、runtime isolation 与 full_live_gate_passed 仍为 false。上游状态仍 12 implemented / 46 planned / 3 unverified。named ACL、任意 wildcard、完整 TCP/端口别名、VLAN name/native VLAN 与多设备 router 子接口仍有缺口；完整复现目标仍未完成。
