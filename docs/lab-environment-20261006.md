# 真实实验 SID 的进程环境边界

日期：2026-10-06。接续用户明确授权的后台只读环境采集，没有扩大为 HCL/guest 启动或系统变更授权。

第一份身份/资产结果已取得且继续沿用，本轮不重复文件清单或全部测试。新观察只获取同一真实SID1006的 USERPROFILE、HOME、HOMEDRIVE/HOMEPATH、APPDATA、LOCALAPPDATA、TEMP/TMP、VBOX_USER_HOME 和有效执行策略，不收集其他环境变量或凭据。

真实回读发现：USERPROFILE、APPDATA、LOCALAPPDATA 为实验账号路径，TEMP/TMP 为其8.3短名路径；HOME/VBOX_USER_HOME 未设置。但 HOMEDRIVE/HOMEPATH 组合最初是 C:/Users/Public/Documents/MCP_HCL_Lab_ReadOnly_20261006，即执行器当时的公共工作目录。Windows 的跨凭据进程创建在未设置home组合时会按工作目录补齐它们，见 [CreateProcessWithLogonW 官方说明](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw)。是否影响具体 HCL 旧组件尚未证实，因此未启动 HCL 来试探。

执行器现在从 Win32_UserProfile 的实际SID→LocalPath记录取得 C:/Users/MCPHCLLab，并仅将子进程 WorkingDirectory 设置为该目录。没有设置 HOME、USERPROFILE 或 VBOX_USER_HOME，没有更改用户环境、ACL或执行策略。复核同一SID后，USERPROFILE和 HOMEDRIVE/HOMEPATH 均为 C:/Users/MCPHCLLab，其余账号目录正确；执行策略仍 Restricted。此修正是使用真实账号正常工作目录，不是把主账号环境伪装成实验身份。

首次和复核分别保留在 work/lab-profile-readonly-20261006/05b0bf67fae3435ba13bfd1e5399a976/ 与 51eb214743044755ab5e05f492df4c17/；汇总 work/lab-environment-verification-20261006.json。观察内容 scripts/hcl_lab_environment_identity.ps1 的 SHA256 为24baca3a7c4e16d4a4a7bacb0de1b9628f41f71348cdfc43619adb9f2cffa3f4；执行器仅允许两个固定、按哈希核验的只读观察脚本。密码仍SecureString输入，不在argv/文件中。PID39184已退出，实验profile Loaded=false。

这是运行命名空间准备的真实新证据；不能提升 runtime_isolation_verified 或 activation_allowed。HCL首次初始化及完整生命周期的实际根/注册/父盘/清理范围仍未验证，物理流量和重启仍未验收。此前单设备成功启动结果继续沿用，不为了兼容性再跑一遍。下一项真实试验须是有明确前后保护清单的最小隔离门槛，并遵守用户触发和已有授权范围；MCPHCLLab仍待必要真实测试结束后按创建SID清理。
# 2026-10-06 后续宿主差异

用户后来明确表示空闲、允许接管本次生命周期。启动前发现：同一跨账号脚本由 PowerShell 7 调用时，真实 SID/profile 虽仍为 MCPHCLLab，USERPROFILE/APPDATA/TEMP 等却继承原账号；只读回执 8335007153ee4e5bbb01d597f24c2772 保留此负面结果。该结论限定本次调用，不以历史 Windows PowerShell 5.1 的通过快照覆盖它。

改在 Windows PowerShell 5.1 宿主中调用后，两个新启动前回执 73fcd022f82242d8b499733e9b50c1e8 和 f37f1f638a9f419ea395225670f42951 均核对真实 SID、USERPROFILE/APPDATA/LOCALAPPDATA/home 与实验 profile 一致，TEMP/TMP 为该 profile 的短名，没有环境覆盖。观察启动脚本现在在非 Desktop 5.1 宿主提前拒绝，解析与凭据输入前拒绝检查通过；没有追加完整回归或再次采集相同清单。

这是启动宿主限制及路径检查，仍不是 HCL 生命周期或运行时清理隔离证明。真实启动后来被启动器的 UAC 请求阻挡，详见 [当前生命周期记录](isolation-trial-execution-20261006.md)。下列历史正确 home 观察仍只证明其原调用条件。
