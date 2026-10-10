# 隔离准备与启动前记录：测试已交接

最新状态：2026-10-06，用户侧时区 Asia/Tokyo。使用者将测试交给 DeepSeekHarness 下的 DeepSeek；Codex 停止测试。交接收尾只读查询时，HCL/Wrapper/MultiCC/VBoxSVC/guest 和本次两个采集进程均未运行，实验 profile Loaded=false。详见 work/isolation-lifecycle-20261006/c9ca01c8a6cd44cd912821143860d320/handoff-state.json。不能由进程消失或控制器超时推断正常生命周期通过。

## 启动器失败、错误身份与恢复

最早两次启动前失败仍保留：PowerShell 7 跨账号启动继承原环境，被校验拒绝；Windows PowerShell 5.1 中实际路径通过，但审阅副本读取被文件权限拒绝。新的输入目录按原字节写入，原 ACL 未改。记录操作 53842551bec243e3b48eecb0748a9b73、73fcd022f82242d8b499733e9b50c1e8 和只读环境观察 8335007153ee4e5bbb01d597f24c2772。

操作 f37f1f638a9f419ea395225670f42951 调用 H3C Cloud Lab.exe 出现 UAC。用户随后输入管理员凭据，后台改以原账号 SID1001 运行；未打开实验工程、未启动 guest。自动正常关闭输入没有生效，用户手动完全退出。退出再次触发既有厂商清理：原 47 个运行时文件及 Base 注册被移除。负面保护差异保存在 administrator-close-verification.json。

按既有备份，仅恢复缺失的 47 文件，已有 5 文件未覆盖；再 registervm 恢复原 Simware_Base UUID。52 文件、原工程目录与原注册全部内容和本次启动前一致；boot.vdi/msr36_b75.vmdk 全量内容一致，其他厂商盘只检查大小和前64KiB。lock.ini 及12个厂商盘时间戳变化保留，未伪造还原、未写厂商文件。回执为 work/isolation-lifecycle-20261006/f37f1f638a9f419ea395225670f42951/restoration-verification.json。

## 普通权限客户端：只证明初始化身份

只读 PE 资源解析确认启动器为 requireAdministrator，SimwareClient.exe/SimwareWrapper.exe 为 asInvoker；没有修改 manifest、兼容层或系统安全设置。经现有客户端入口正常启动的操作为 c9ca01c8a6cd44cd912821143860d320。实际实验 SID1006 查询确认 Client、Wrapper、MultiCC 和 VBoxSVC 都属于该实验 SID，USERPROFILE/APPDATA/home 路径正确；主账号不能读取 VBoxSVC owner 时没有猜测其归属，由实验账号自身查询补齐。

bootstrap/snapshot.json 记录实验 runtime 仅 lock.ini、0条注册；没有设备 VM。已准备的唯一工程在 C:/Users/MCPHCLLab/Documents/HCL_Trials/Isolation_c9ca01c8/v7_sw_vlan_basic/v7_sw_vlan_basic.net，只有 MSR36-20 LabIsolationRouter，无链路/地址/服务。四个必要输入复制已核对，只改新副本 workingdir；未引用的旧 cfg/ConfigDisk 未复制，实验 cfg 为空。GUI 停在空的打开文件对话框，尚未输入工程路径或打开副本，因此没有真实设备创建/启动/停止证据。

两个隐藏采集进程后来达到期限，controller-stderr.txt 和 watcher-stderr.txt 的负面结果均保留。收尾时无上述进程和 guest，profile 未加载；未重复采集实验资产或重启 HCL。主账号当前52文件清单/元数据、小型描述符和注册哈希与恢复后一致，见 handoff-main-assets.json；此收尾未重读大磁盘字节，最后完整字节核验沿用恢复回执。

## 接手范围

使用者将测试交给 DeepSeekHarness 下的 DeepSeek。先做已审阅的一次单设备生命周期隔离，沿用软件及历史有效结果，保留失败，不扩大成配置、网络、批量型号或无线的重复试探。客户端普通权限身份通过不等于完整生命周期清理隔离；原生 CLI/配置/网络及全61/5等价仍未完成，runtime_isolation_verified=false、full_live_gate_passed=false。

账号启用、创建 SID/唯一标记仍匹配，尚未删除，因为后续必要真实测试仍需使用它。全部必要真实测试完成后按创建回执 SID 停用并删除账号，保留 profile/VM/证据；这是已有条件授权，不重复索取。创建回执与回退脚本见 docs/account-creation-20261005.md、docs/lab-account-review-20261005.md。
