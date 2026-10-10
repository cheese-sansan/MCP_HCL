# 编号和命名 ACL 删除事务

日期：2026-10-06；8a46 独立工作区，detached 9963ddc，未提交。

新增 hcl_remove_acl(project_path,topology,device,parameters,dry_run=false)，实际发现面46工具/6资源。parameters 为二选一 number/name、可选 acl_type、binding_interface 和 binding_direction=inbound/outbound。按 Comware 编号范围核对类型；命名类型可由真实完整配置解析。dry_run 缺少命名类型时明确 unverified/requires_current_acl_type，不生成虚假的已验证删除命令。

实际操作先核对目标 VM/管道身份、备份、启动文件与恢复预检；可选绑定只撤销本次 IPv4 接口/方向与目标 ACL 的精确编号/名称别名，再删除完整定义。命名头失去名称但仍保留原编号定义不算删除成功。其他 ACL、反方向、ipv6/mac、MTU/地址等配置受完整范围比较保护，不能为了通过而扩大解绑。原生设备对应用中 ACL 的删除行为仍待实际观察；若固件引起范围外变化，恢复并保留失败，而不是宣称 PT 语义等价。

删除后读取完整当前配置，并另存、选择和比较新的主用启动内容。失败仅在原 VM UUID 的新连接恢复运行配置与原启动指针，不重放删除。所有错误、旧连接历史、原备份及失败恢复都保存。

固定上游 remove_acl_uc 实际位于 application/use_cases/apply_acl.py（不存在独立 remove_acl.py）；GitHub 连接器按 846db381bc2c6ee0229d56e1d7ce8847eb6b213d 读取，缓存 Git blob 精确匹配 0d69483afaee2c466558165f7810541451392151。它表达可选解绑、ACL完整删除和write memory。Comware undo acl / undo packet-filter 的语法参考[H3C ACL 命令](https://www.h3c.com/en/d_202106/1419044_294551_0.htm)；没有修改厂商文件或镜像。

仅新增必要检查：8项删除/范围/恢复/stdio专项通过（2.834秒），3项发现/默认门控依赖通过（5.053秒），没有重复完整回归或真实设备启动。软件包45个包文件匹配源码；wheel SHA256 f173376858f8467443fbfe74748b039b8b82bcb0c4bdd82f63741112f72ae62b。独立导入、46/6发现面和默认门控通过。公共包 C:/Users/Public/Documents/MCP_HCL_Lab_20261006_ACLRemoval 清单已核对，旧包保留；无厂商资产、依赖wheel、凭据或用户配置。

这些是软件合同，模拟通道只提升 protocol_*，真实配置/持久化/恢复、应用引用行为和 PT object API 等价均未验明。上游仍12 implemented/46 planned/3 unverified，full_live_gate_passed=false。实验账号真实只读初始基线已获得，见[采集记录](lab-profile-observation-20261006.md)，仍不代替运行时清理隔离或网络验收。
