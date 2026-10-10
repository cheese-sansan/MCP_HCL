# GUI 打开/保存的身份与运行时前置保护：待 DeepSeek 测试

2026-10-07，Asia/Tokyo。修订nat-transactions工作区的hcl_open_project/hcl_save_project，声明53工具/6资源不变。本轮未执行功能、单元、模拟、SDK发现/调用或原生采集/GUI测试；只做语法、C#助手编译及候选构建。原账户资产、HCL程序/镜像、历史回执和旧候选保留。

## 具体问题和实现

旧中继检查PID名称、活动工程caption和文件回读，没有核对实际SID、提权令牌、后端监听者或用户运行时资产。此前UAC使HCL改以原账号运行并清理47个历史文件/Base注册的失败已记录；本次不重跑该失败，也不把工程副本解释为运行时隔离。

新collector只读取得当前WindowsIdentity、CIM登记的SID配置目录、HCL进程所有者/创建时间/会话/可执行路径及令牌提权状态。调用者和HCL必须是同一SID/会话且均非提权；调用者已知文件夹、环境的profile/AppData/Temp必须符合CIM真实目录。继承的profile/Temp在C#编译使用Temp之前先检查。可执行文件须匹配配置安装根的SimwareClient.exe，文件哈希用于前后绑定，不声称已验证进程内加载的每个字节。

还采集本机默认16600端口的唯一监听者，要求其为同SID/会话、非提权的配置SimwareWrapper.exe；前后固定PID/创建时间/路径/磁盘文件哈希。自定义GUI后端端口尚无接受证据，活跃GUI请求返回gui_backend_port_unverified；离线工具与后端自身配置不因此被禁止。监听者身份不证明GUI实际连接了它，gui_backend_connection_verified仍false。

打开前检查当前SID的HCL VMs与VirtualBox注册：除根lock.ini外，已有文件、目录或任何机器注册均拒绝；拒绝不会删除、移动或注销这些资产。打开前在Python和GUI动作端再检查。首次空空间观察不是厂商清理边界证明，runtime_isolation_verified始终false。

保存只复用当前MCP进程内、同一HCL/后端身份、同一工程和阶段operation_id的许可；进程/二进制/阶段变化使其失效。许可可在动作尚未获得结果前准备，但不能证明打开成功；save仍必须重新验证活动caption及实际文件回读。服务器重启、已有未经许可的运行资产或更换工程不自动迁移/接管，也不自动重放打开操作。

GUI控制器本地锁和当前配置目录.mcp_hcl/gui-control.lock的Windows文件锁均为非阻塞；忙则拒绝，不排队过时动作。在账号共享锁内再做前置检查。它只串行化本软件的GUI中继，不能锁住手工操作或其他后端API。

动作端在按钮、路径输入与截图前复核SID/令牌/创建时间/监听者，并校验collector文件哈希；操作后再次采集身份。不再传ExecutionPolicy=Bypass；使用系统Windows PowerShell执行可信包内脚本主体，参数以常量UTF-8编码表达，用户路径不作为命令文本解释。没有修改用户执行策略、安全设置、凭据或用户环境根。

## 证明边界

当前profile/AppData/Temp事实来自调用者，不是远程读取HCL或Wrapper自己的环境块。hcl_environment_verified=false；Wrapper/VBoxSVC/guest自身环境和实际清理边界仍需必要真实证据。其他设备电源、控制台、后端操作没有在本次补成同一个全局生命周期保护，不能扩大此GUI前置检查的范围。

模拟依赖不提升原生project_identity_verified；新的actor回执还须有process_identity=true。只有文件层/GUI工程身份的限定结果，live_canvas_verified、guest/config/connectivity和full_live_gate_passed不提升。两上游行仍planned，12 implemented/46 planned/3 unverified不变，完整61/5复现仍Incomplete；保存文件不能充当已验证的原生设备/线缆库存。

本轮Python AST、两PS脚本语法、令牌助手C#编译检查完成；没有调用令牌方法或collector。候选wheel/源码字节核对单独记录，均不是功能或安全验收通过。

## DeepSeek 必要检查

- 同/异SID、未知所有者、提权令牌、会话/创建时间/PID变化、客户端/监听者路径与文件变化、监听端口无/多/异账号或权限未知。采集失败必须在GUI输入前停止，不输入管理员凭据或扩大权限。
- 继承错误profile/AppData/Temp、不可读/链接目录、已有VM文件/空目录/注册；不得以Test-Path的False或缺字段认定为空。仅lock.ini的初始空间、同进程许可保存、服务器重启/阶段变化及未知完成状态分别检查。
- 并发GUI控制器、共享锁失败、动作端身份复核、collector哈希、Unicode/引号/控制字符参数、超时/回执失败和模拟来源分离。旧mock runner的参数解析需适应inline主体，旧正向模拟回执不再证明原生GUI成功。
- 只检查受本次变化影响的合同/失败路径；真实生命周期沿用既有单设备必要范围，保留负面结果，不重跑旧成功guest启动或无变化的完整回归。

测试由DeepSeek Harness中的DeepSeek负责。全部必要真实测试完成后，按创建SID/唯一标记停用并删除MCPHCLLab，保留profile/VM/证据的条件授权不变。当前不据此软件稿清理账号或宣告真实隔离完成。
