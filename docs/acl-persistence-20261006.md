# ACL 未命中动作与启动配置持久化

日期：2026-10-06，Asia/Singapore；工作跨越午夜，初始专项日志仍保留 20261005。8a46 工作区，detached 9963ddc，修改未提交。本轮接续 [命名 ACL](acl-named-20261005.md)。

Acl.implicit_deny 默认 true；缺少 catch-all 时，在 ACL 内增加最后的 deny 规则（ID 65534），不修改全局 packet-filter 默认动作。显式 permit/deny catch-all 或已有 catch-all 按原含义保留；末尾编号被其他条件占用且无法表达回退时，在修改前拒绝，不覆盖无关规则。implicit_deny=false 是显式沿用 Comware 规则集合的扩展选项，不自动移除已有规则。生成、实际基线编译、范围保护和回读均检查派生规则。

配置成功后另存本操作的唯一 after.cfg；比较其内容，再选择为主用下次启动配置，并比较 display startup、display saved-configuration 和运行配置。保存完整运行配置对应上游 write memory 的语义。原 current/main/backup 文件及哈希在操作前捕获并保护；原启动配置可以与运行配置不同。多设备部署在全部配置回读通过后才进入持久化。

失败恢复既核对运行配置，也恢复原 main/backup 指针，包括 NULL。undo startup saved-configuration 只清除指针，不删除配置文件。原启动文件改变或恢复不完整时保留错误及本地基线，不报告完整回退。首次备份 save 的结果未知时，已有启动快照可用于恢复；未经内容核验的 guest 备份不能用于 configuration replace。所有 replace 的保存询问明确回答 N，避免恢复流程另行覆盖旧启动文件；非法确认值在发送命令前拒绝。

语义依据来自固定上游 acl_cli_generator.py、HCL 自带配置文件帮助 D:/HCL/CMD-help/-129396861/1324839659/-1051814356.htm（SHA256 52ca8680ee23a329a737f7ea2b49f5c8ad9ce9f004bb6702c0c93d3cbcddd218）、[Cisco ACL 默认拒绝说明](https://www.cisco.com/c/en/us/support/docs/ip/access-lists/26448-ACLsamples.html) 和 [H3C 配置文件管理命令](https://www.h3c.com/cn/d_202104/1400837_30005_0.htm)。本机厂商文档未修改，也未复制入仓库。分布式/IRF、多存储成员或未知启动输出仍拒绝推断；本轮不能声称所有型号适用。

本轮只补测必要的新边界：11 项专项通过；共享控制台、生成及部署模块改动后，运行一次完整回归，共 238 项，237 通过、1 Windows symlink 权限跳过，72.406 秒。日志 work/acl-persistence-regression-20261006.txt；前 43 项兼容检查和首次失败记录保留。已有实测启动不重跑，没有额外真实设备、网络或重启测试。

wheel SHA256：6a3a8389dc62dc7d650d05b2f3bab59931844b91b0acd0df9300f35b2ee55fbb。42 个包文件匹配源码；独立 wheel 的 44 工具/6 资源、默认 implicit_deny Schema 和 writes_disabled 门控通过。公共准备包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_ACLPersistence 的复制后清单已核对；旧包保留。包不含依赖 wheel、密码、厂商或原用户资产。

上述是软件合同和合成状态机证据。原生 configuration/persistence/recovery、真实启动后的保留、包过滤流量及完整 61/5 功能等价均未验明；full_live_gate_passed=false，上游仍 12 implemented / 46 planned / 3 unverified。不得把配置文件比较当作重启或流量通过。

用户于 2026-10-06 明确确认 MCPHCLLab 用于测试，并授权在必要真实测试结束后停用、删除此账号；仅做必要验证，沿用已有有效结果。创建回执中的 SID 与唯一标记是删除依据，不按名称猜身份，不重复索取这项授权。账号删除不包括其配置目录、VM 或历史回执。当前真实测试尚未结束，删除待执行，账号暂留；这项清理也是完整交付的后续要求。

本轮后续读回观察到实验 SID 的真实 profile_count=1、LocalPath=C:/Users/MCPHCLLab、Loaded=false，HCL/guest 与 runningvms 为空。当前调用账号访问此目录被拒绝，runtime 只读结果为 unknown；没有改 ACL、加载实验配置或启动 HCL。新 profile 已生成，接下来需要其自身会话的环境证据，不能继续说“配置目录尚未生成”，也不能推断目录为空。

这次观察还发现 runtime.exists 路径探测会把访问拒绝误作不存在，最初原始结果错误报告 observed/file_count=0。该负面回执 work/lab-runtime-observation-20261006.json 保留；修复后先证明 profile/registry 命名空间可枚举，再判断文件存在，只捕获真正的 FileNotFoundError。五项相关测试通过，0.050 秒，并沿用已通过的其他模块回归，没有再次运行完整回归。实际同一目录现在返回 unknown/WinError 5，无 file_count 结论，见 work/lab-runtime-observation-fixed-20261006.json。

包含该隔离观察修复的最新包为 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_ACLPersistenceRuntime，wheel SHA256 335511d9a0b016c1be4c29f3ca2cf4f0d463670f11b4513f03017355fcf5bea0。42 个包文件匹配源码；与之前通过完整回归的包相比，仅 mcp_hcl/runtime.py 有变化，已独立导入验证，其余发现面/Schema/门控结果沿用。前一包及 238 项完整回归保留为各自的历史快照，不能把本次五项检查称为新的完整回归。
