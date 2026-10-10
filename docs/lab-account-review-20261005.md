# 本机专用 Windows 实验账号：创建与回退审阅稿

日期：2026-10-05，Asia/Singapore。本文保留最初的可审阅步骤。使用者随后明确指定账号和测试密码，已执行 Create；当前事实见 [账号创建记录](account-creation-20261005.md)。停用/删除未执行，HCL/guest 未启动。

2026-10-06 用户补充授权：必要真实测试结束后，按创建记录的 SID 停用并删除测试账号；不重复索取同一授权。仅做必要验证，沿用已有有效结果。账号目录、VM 和回执保留，不属于本次账号删除范围。

2026-10-06 最新 profile_count=1，LocalPath=C:/Users/MCPHCLLab、Loaded=false。当前调用账号无法枚举该目录，实验 runtime/注册清单仍 unknown；第一次配置目录生成这一步已观察到，不重复执行。后续身份与环境检查应在实验账号会话进行，不能把访问拒绝当作空资产。

2026-10-06 后续用户授权后台执行上述只读采集，真实MCPHCLLab SID会话已回读0个runtime文件/0条注册，无HCL/guest和观察错误；该初始基线可沿用。操作及两次失败见 [采集记录](lab-profile-observation-20261006.md)，不修改执行策略或目录ACL。后续仍须最小必要的生命周期/CLI验证，不能把空的初始命名空间提升为已隔离。

## 拟采用的边界

候选账号 **MCPHCLLab** 为本机标准用户，只加入内置 Users 组（SID S-1-5-32-545），不加入 Administrators。密码由使用者在创建时安全输入，不放入命令行、Git 或回执。

首次交互登录后，Windows 为新 SID 建立真实用户配置目录。预计为 `C:/Users/MCPHCLLab`，必须以实际读回为准；不通过修改 HOME、USERPROFILE 或 VBOX_USER_HOME 冒充独立身份。

原账号 `w8p1p` 的工程、`C:/Users/w8p1p/HCL VMs`、`.VirtualBox/VirtualBox.xml`、52 个历史文件、原 Base 注册及备份都是保护对象。HCL 与 VirtualBox 安装仍为 D:/HCL 和现有 6.1.50，本步骤只准备账号身份；厂商镜像、系统驱动、BCD、安全功能和重启不在本步骤内。

**新账号是隔离候选，不是隔离已经通过。** HCL 16600 端口、topo1 管道名、厂商镜像与部分安装日志仍可能共享。两套 HCL 不可并行；真实启动前还需验明实际 runtime 根、VBox 注册归属、Base 与磁盘父子引用，以及厂商清理前后的保护资产。

## 本轮已完成的只读核对

- 最初 Preview 时没有 MCPHCLLab 用户或同名本地组；现已创建标准账号，预计配置目录仍未生成。
- 内置 Users/Administrators 组已按 SID 读回，避免系统语言导致组名猜测。
- 当前实际安装为 VirtualBox 6.1.50；运行 guest 为空。
- 新 runtime preflight 观察到 52 个原文件和一条原 Base 注册，返回 runtime_ready=false、runtime_isolation_unverified、existing_runtime_assets。
- 脚本通过 Windows PowerShell 语法解析和 Preview 测试；Create 已实际执行并独立核对，Disable/Remove 尚未实测。

## 1. 审阅预览与脚本

脚本位置：

`C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/scripts/hcl_lab_account.ps1`

已生成的计划回执：

`C:/Users/w8p1p/.codex/worktrees/8a46/MCP_HCL/work/lab-account-review-20261005/8f2a1156efb74cbca7707e176d270150/result.json`

重点核对 account_name、owner_sid、owner_profile、protected_runtime、protected_registry 和 proposed_group_sid。若希望更换账号名，重新运行 Preview 生成独立回执；不改写旧回执。

脚本默认 Action=Preview。它只读取用户/组状态并写入新回执目录，不调用账号修改命令。

## 2. 获得创建授权后，手动创建标准账号

此步骤已通过同一 owner 的 Windows 提权助手执行，密码经受保护的内存通道传递。下面保留手动执行方式供审阅；现有账号不需要重新 Create。原手动方式是在 **64 位、管理员 Windows PowerShell** 中，以原 w8p1p 身份提权执行：

```powershell
$accountScript = 'C:\Users\w8p1p\.codex\worktrees\8a46\MCP_HCL\scripts\hcl_lab_account.ps1'
$accountPlan = 'C:\Users\w8p1p\.codex\worktrees\8a46\MCP_HCL\work\lab-account-review-20261005\8f2a1156efb74cbca7707e176d270150\result.json'
& $accountScript -Action Create -AccountName 'MCPHCLLab' -RecordFile $accountPlan
```

创建动作会重新核对账号/组/配置目录仍未占用，要求原 owner SID 与用户配置一致，并拒绝在 HCL、终端或 guest 仍运行时执行。密码通过 Read-Host -AsSecureString 由使用者输入。

成功回执必须为 status=created_standard_account，含实际 account_sid 与唯一 description 标记。**保存返回的 record_file**；它是之后停用/删除的身份依据。若部分失败，检查保存的 partial 回执，不重复 New-LocalUser，不凭异常推断账号不存在。

本步骤未自动登录、创建用户配置目录或启动 HCL，也未复制原 Base 或修改原账号。Microsoft 的 [New-LocalUser 文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.localaccounts/new-localuser?view=powershell-5.1)说明密码接受 SecureString；本地模块需 64 位 PowerShell。

## 3. 使用者首次登录新账号并核对身份

在主账号保存工作、确认 HCL/guest/终端已正常退出后，由使用者切换或注销并登录 MCPHCLLab；不要自动切换会话或终止他人的进程。

在新账号普通权限 PowerShell 中只读检查：

```powershell
$labIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$actualLabProfile = [Environment]::GetFolderPath('UserProfile')
[pscustomobject]@{ Name=$labIdentity.Name; SID=$labIdentity.User.Value; Profile=$actualLabProfile }
& 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe' --version
& 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe' list vms
& 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe' list runningvms
```

实际 SID 必须等于创建回执中的 account_sid，且不同于 owner_sid。第一次启动 HCL **之前**，新账号不应含原 Base、历史拓扑或其他账号注册。VBoxManage 可能生成新账号的空全局配置，这是注册配置初始化，不是 guest 启动。

若发现旧注册、配置目录复用、身份错配、继承 VBOX_USER_HOME、原账号的 VM/磁盘引用，立即停止。不要复制主账号 HCL.ini、gen_py、.VirtualBox 或 HCL VMs 来消除缺项。

## 4. 在新账号自己的目录准备 MCP

使用新账号自己拥有、可运行的 Python **3.12+** 和独立 venv。项目元数据最低为 3.11，但 Windows 原生非阻塞管道的本轮验证使用 3.12；其他版本需另外验证。不要复用位于 w8p1p 私有缓存或工作区的 venv。若新账号没有解释器，先安排独立解释器准备，不更换系统 Python。

使用者可把本轮生成的独立软件准备包搬到新账号能够读取的位置，例如 Public Documents 下新建的专用目录。包内只含本项目 wheel、固定实验请求和依赖清单，不含厂商程序、镜像、原用户配置或密码。新账号确认可读后复制到自己的 Documents；不扩大现有用户目录的 ACL。

已准备并校验的最新包目录为（2026-10-06 NAT 模式实现后）：

`C:/Users/Public/Documents/MCP_HCL_Lab_20261006_NatModes`

其中 wheel 的 SHA256 为 `65bc0c3b41bdabbddd5c1cdcd0782f17621f5de73d6b9f78dbe5907895e1ff41`。45 个包文件逐字节匹配当前修改后源码；46 工具/6 资源发现面通过。旧包保留为各自的历史资产。包不含依赖 wheel，第一次在实验账号安装仍需可用包源或另备依赖。当前包的 runtime_ready=false。

在新账号中创建自己的 Projects、Staged 与 Receipts 目录，设置 MCP_HCL_PROJECT_ROOTS/MCP_HCL_OUTPUT_ROOT 到这些真实目录。MCP_HCL_ALLOW_LIVE_WRITE 继续为 0。先安装 wheel、检查依赖，再运行：

```powershell
# 将解释器与 venv 路径替换为该实验账号已经核实的实际位置。
& '.\.venv\Scripts\python.exe' -m mcp_hcl.lab_bundle preflight --installation 'D:\HCL'
```

preflight 输出只是当前资产与环境观察。即使新账号没有历史 VM，runtime_ready 与 runtime_isolation_verified 仍为 false；不能据此直接开始批量实验。

## 5. 另行安排最小隔离验收

创建账号的批准不包含真实 guest 或长时网络验收。之后由使用者明确触发隔离验收，先生成当前主账号保护资产的最新清单，再观察新账号首次 HCL 初始化、独立 Base 与 runtime 根；核实没有自动载入原工程。

仅新建本次实验设备和工程，逐项记录其 .vbox、镜像及差分盘引用、管道、拓扑名和 UUID。一次完整创建/启动/停止/退出之后，对主账号的工程、52 文件、注册与厂商原镜像做前后核对。缺一项都不能报告隔离通过。

不得打开或启动原 Simware_Base。GUI 已经成功启动单台设备的历史证据继续沿用；新试验的用途是证明新命名空间与 CLI 缺口，必须使用新 operation_id 和目录。

只有隔离门槛通过，才进行一次只读 display 命令回读；之后按双设备 → 固定三路由器 → 混合型号推进。无线另有真实安全关联、设置持久化和恢复门槛。

## 6. 回退

先在实验账号内正常停止本次 guest、关闭 HCL 和自己持有的终端，保存新账号的注册清单、VM/配置、日志及回执，然后注销该账号。回到原 w8p1p 账号的管理员 PowerShell。

以 **创建动作返回的实际 creation record_file** 设置变量；不能使用 Preview 回执、不能按账号名猜 SID：

```powershell
$accountScript = 'C:\Users\w8p1p\.codex\worktrees\8a46\MCP_HCL\scripts\hcl_lab_account.ps1'
$creationRecord = 'C:\Users\w8p1p\.codex\worktrees\8a46\MCP_HCL\work\account-creation-20261005\748abd1c1434409d8b9ab95e0f37c68c\account-receipts\3a42945c83794fcabde4763c5def3e8c\result.json'
& $accountScript -Action Disable -AccountName 'MCPHCLLab' -RecordFile $creationRecord
```

停用是优先回退：可以停止新的登录并保留审计资产。脚本核对实际 SID、账号名、唯一 description、原 owner SID、无 HCL/guest 进程、实验配置未加载且不是系统配置；任一不符即拒绝操作。

确认无需再登录且证据已保留后，移除同一账号：

```powershell
& $accountScript -Action Remove -AccountName 'MCPHCLLab' -RecordFile $creationRecord
```

Remove 要求账号已停用，并按保存的 SID 操作和回读，不会按同名新账号继续删除。参见 [Remove-LocalUser 文档](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.localaccounts/remove-localuser?view=powershell-5.1)。

**停用/删除账号都保留用户配置目录、VM 和回执**；不递归删除 C:/Users、不卸载 VirtualBox、不恢复/覆盖原用户注册。若以后要清理残留用户配置，需单独核对实际 SID→LocalPath、未加载状态、磁盘引用和备份后再制定删除方案。

最后回读主账号的原 Base UUID、runningvms、工程与 52 文件清单。用户身份回退不证明实验期间的所有设备配置恢复；如果发现原资产变化，停止并按既有备份恢复方案处理，不继续批量验收。

## 审阅后应明确的下一步

MCPHCLLab 标准账号已经创建并读回。下一步由使用者首次登录，核对实际 profile 和独立环境；真实 HCL 初始化、guest、网络验收及残留配置删除均有各自后续门槛。账号回退操作尚未执行、尚未真实验证。
