# MCPHCLLab 标准账号创建记录

2026-10-06：用户明确授权在必要真实测试完成后停用并删除此测试账号，同时要求仅做必要测试、沿用已有有效结果。清理尚未执行；账号、配置目录和回执分别处理，不额外删除 VM/证据资产。

最新独立读回：账号启用，profile_count=1，实际 LocalPath=C:/Users/MCPHCLLab，Loaded=false；HCL/guest 与 runningvms 为空。配置目录已生成，当前调用账号对该目录访问拒绝，实验账号 runtime/注册尚未取得可读清单；不能当作空目录或隔离通过。下列 profile_count=0 是创建当时的历史观察。

后续用户授权由Codex后台执行只读采集，已取得实验账号真实SID会话输出：0个运行时文件、0条注册、没有HCL/guest进程或观察错误；观察子进程已退出且profile卸载。见 [实际采集记录](lab-profile-observation-20261006.md)。原账号的目录访问拒绝仍存在，真实初始基线已补齐；完整运行时清理隔离仍未通过。

后台执行器工作目录已按该SID的CIM profile修正，USERPROFILE及home组合均真实指向MCPHCLLab，执行策略保持Restricted；详见 [环境检查](lab-environment-20261006.md)。没有手工覆盖用户环境变量，资产结果沿用，账号清理仍待必要真实测试结束。

日期：2026-10-05，Asia/Singapore。使用者在账号创建批准问题后明确指定本机标准账号及测试密码，作为本次创建授权；密码不写入此文档、Git、命令行参数或工作回执。

## 已执行及独立读回

- MCPHCLLab 已创建并启用，属于内置 Users，未加入 Administrators。
- 实际新账号身份保存在私有创建回执，SID 与主账号不同。未来停用/删除只按该回执的 SID 和唯一 description 标记操作。
- 新用户 profile_count=0，预计配置目录尚未生成；没有自动登录、切换会话或加载该用户配置。
- HCL、guest 未启动。VirtualBox 仍 6.1.50r161033；原 Simware_Base UUID 7ac3bddb-1356-4121-b70a-fd14a8bd8a94 保持注册，runningvms 为空。
- 主账号 52 个运行时文件的路径/大小/时间元数据、VM 描述符哈希及全局注册哈希与本轮前的快照一致；没有重复读取全部大磁盘字节。原工程 .net 哈希仍 CCC821A5FBA6F30AE0F20CBB5FB4029D39A9D5812068B6B40047A1E85A785570。

创建通过隐藏的 Windows 提权助手执行，凭据通过限定原 owner 的命名管道传递，载荷使用 [CurrentUser DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)，收件进程 PID 核对后才发送。没有凭据文件或命令行密码；合成运输测试先通过，真实助手随后完成。系统密码策略未被修改。

创建回执：

`C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/work/account-creation-20261005/748abd1c1434409d8b9ab95e0f37c68c/account-receipts/3a42945c83794fcabde4763c5def3e8c/result.json`

同一操作目录还有 broker.json、independent-account-readback.json、original-runtime-check.json。回退步骤仍见 [账号审阅稿](lab-account-review-20261005.md)；Disable/Remove 未执行、未真实验证。

## 使用者下一步

配置目录和真实账号只读初始基线已取得，无需重复登录或采集同一结果。下一步按既有门槛安排必要的 HCL 生命周期隔离和 CLI 验收。账号已创建，不需要再运行 Create；测试结束后的账号清理授权已记录。

最新软件准备包已放在：

`C:/Users/Public/Documents/MCP_HCL_Lab_20261006_NatModes`

最新 NAT 模式 wheel SHA256：65bc0c3b41bdabbddd5c1cdcd0782f17621f5de73d6b9f78dbe5907895e1ff41。45 个包文件匹配源码，包的清单哈希已校验，不含厂商程序、镜像、原用户配置或密码；旧包全部保留。新账号实际读取和安装尚未验证；它需要自己的 Python 3.12+、venv 和可用依赖包源。软件验证见 [持久化记录](acl-persistence-20261006.md)。

新账号登录后的第一步是核对实际 SID/profile、VBox 注册归属与 runtime 根，再准备自己目录下的 Projects/Staged/Receipts。实时写开关保持关闭。不能复制原账号的 HCL VMs、注册或 gen_py 来填缺项，也不能仅因目录为空而认为隔离通过。

之后的 HCL 初始化、完整生命周期隔离与 guest/网络验收仍按使用者触发和既有门槛进行。账户身份准备不是运行时隔离证明；full_live_gate_passed=false。
