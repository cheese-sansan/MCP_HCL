# 已授权的实验账号只读采集

日期：2026-10-06，Asia/Singapore。用户在收到实验账号采集请求后明确授权由 Codex 执行，自己继续其他工作。此授权仅用于该只读采集；没有扩大为 HCL 初始化、guest 启动、系统或镜像修改授权。

已在隐藏的 MCPHCLLab 子进程中执行核验过的观察内容，未切换桌面。实际回读 account=Kurumi/MCPHCLLab、SID=S-1-5-21-246709277-55761766-931132026-1006、profile=C:/Users/MCPHCLLab；runtime_file_count=0、registered_machine_count=0、processes/errors/blockers 均为空。不是以主账号更改 USERPROFILE 或读取一个同名目录来模拟身份。

操作指针 work/lab-profile-readonly-20261006/4c1dbce97811466e891c3443d19d5c90/；stdout.json 是该账号真实输出。私有完整回执为 C:/Users/MCPHCLLab/Documents/MCP_HCL_Receipts/profile-e878f79349be4b2c865beb42ea70719a/profile-observation.json。原调用账号仍未获得该目录的访问权；没有扩大 ACL 或复制用户配置。

采集脚本 scripts/hcl_lab_profile_observation.ps1 的 SHA256 为 7256d14fa55ea27f7e2edf283d55a71e78f2bee97190d20ea363eb4d0cb217eb，公共审阅副本在 C:/Users/Public/Documents/MCP_HCL_Lab_ReadOnly_20261006/。执行器 scripts/hcl_lab_observation_launch.ps1 用 SecureString 读入已提供的测试凭据，密码未进入进程参数、环境值或回执文件；子进程再核对同一内容哈希与真实 SID。

保留两次失败：f80f1ad75bf0499186914e169b9a7fca 的脚本文件加载被执行策略阻止；ea22ba1556914b599a359341917d003a 的过长命令参数在创建进程时失败。第三次用短命令执行同一已校验内容，策略保持现有配置，没有调用 Set-ExecutionPolicy 或使用 ExecutionPolicy=Bypass。[Microsoft 文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies)说明 Restricted 允许命令而限制脚本文件。未把前两次改写为成功，也没有凭观察超时盲目重启同一进程。

执行器的跨凭据 Process.ExitCode 未返回可靠值，因此记录为 terminal_observed；成功结论来自有效、完整、SID 匹配的 JSON 和 errors=[]，不伪造 exit_code=0。PID28884 已不存在，Win32_UserProfile 回读 Loaded=false。这只是后台观察进程结束，不是实际 guest 验收结束。

主账号保护资产仍观察到52个运行时文件、一条原 Simware_Base 注册UUID7ac3bddb-1356-4121-b70a-fd14a8bd8a94；未重新哈希全部大磁盘字节。汇总 work/lab-profile-observation-verification-20261006.json。

这份真实结果解决了“原账号访问拒绝，无法取得实验账号初始清单”的证据缺口。空的初始命名空间仍不证明 HCL 初始化/创建/启动/停止/退出只清理自己的资产，也不证明共享端口、管道和厂商镜像隔离。runtime_isolation_verified、activation_allowed 和 full_live_gate_passed 仍为 false；后续只安排必要生命周期和 CLI 验收，已有有效启动结果继续沿用。必要真实测试完成后按创建 SID 停用并删除账号的授权保持有效。

后续仅新增进程环境检查，发现跨凭据后台进程的home组合由工作目录补齐，已将工作目录设为CIM登记的真实实验profile并核对，见 [环境边界记录](lab-environment-20261006.md)。本节资产清单沿用，没有重复采集。原始公共工作目录回执仍保留，不能据正确SID假定每个home变量都正确。
