# 方案 B：分支内 SDK 试验（2026-10-02）

## 结论

**尚不能判定 HCL 在 VirtualBox 6.1.50 上可运行。** 本轮获得的是分支内执行授权，因此只在 dsh-2 写入探针、测试、下载资产和备份；没有安装、修改系统 COM/驱动、改 BCD、安全设置、重启或启动真实 guest。

方案是原地升级 VirtualBox 以尝试保留 Hypervisor/VBS，但 Windows 上的驱动和 COM 注册属于共享机器状态，不能被 Git 分支隔离。当前安装回读仍为 6.0.14r133895。

## 本轮实际执行

- 下载官方 6.0.14 与 6.1.50 SDK，逐个验证官方 SHA256，不导入或执行 vendor SDK Python，也不实例化 COM。
- 比较 30 个按已观察 HCL 使用面选取的接口成员：29 个声明一致，1 个不同。两版 SDK 的 Python 源文本通过 Python 3.8 语法解析；这不证明它在 HCL 内嵌解释器里实际可用。
- 下载 6.1.50-161033-Win.exe 与 6.0.14-133895-Win.exe。SHA256 与官方下载清单一致，Authenticode 均为 Valid / Oracle Corporation。安装器没有执行。
- 在确认 runningvms 为空后完整备份 HCL VMs 的 52 个文件，并核对原件和副本 SHA256；另备份 VirtualBox.xml。备份字节一致，不代表恢复已经测试。
- dsh-2 回归：69 项，68 通过、1 symlink 权限跳过，18.018 秒。它不是对 Codex 0.5.0 的测试。

详细哈希、原始路径与分层结论见 [验证记录](plan-b-verification-20261002.json)。SDK 比较命令：

```powershell
$env:PYTHONPATH = 'E:\MCP_HCL\src'
E:\MCP_HCL\.venv\Scripts\python.exe -B -X utf8 scripts\hcl_vbox_sdk_probe.py `
  --before-sdk work\feasibility\plan-b-20261002\VirtualBoxSDK-6.0.14-133895.zip `
  --after-sdk work\feasibility\plan-b-20261002\VirtualBoxSDK-6.1.50-161033.zip `
  --output work\feasibility\plan-b-20261002\NEW_SDK_RECEIPT.json
```

## 找到的兼容性差异

1. IMachine.launchVMProcess 的第三参数：6.0.14 是 `environment: wstring`，6.1.50 是 `environmentChanges: wstring[]`。HCL 的 SimwareWrapper.exe 含 launchVMProcess 字符串，但这不能证明实际传参形状；更不能证明旧客户端会自动完成数组转换。
2. MachineState 移除了 FaultTolerantSyncing，后续快照状态和范围值发生变化。基本运行状态未因此被证明不兼容；使用旧枚举处理快照仍存在具体风险。
3. IMachine 接口 UUID 改变。晚绑定可能适配注册后的类型库，但旧 gen_py 缓存和 HCL 内嵌绑定的实际效果仍需执行验证。

因此先前“核心 COM 接口完全不变”“升级必然使 guest 启动”的表述不能作为已验证结论。二进制字符串扫描没有发现版本比较，也不能穷尽地证明 HCL 不会做版本检查。

探针首版曾把空 coclass 引用误当成接口声明，产生缺失成员记录；已修正，并增加回归用例。原始输出 sdk-comparison.json 保留，但明确无效；只使用 sdk-comparison-corrected.json。没有把一次软件探针错误当成实际运行失败。

## 尚未执行的机器级试验

本轮不运行安装器，不清理共享 gen_py，不替换 SDK，不停止宿主服务，不重建启动项。若使用者另外授权升级共享 VirtualBox，仍需保持无自动重启、无启动配置/安全功能修改、原 VM 不用于试验的边界。guest 启动和超过一分钟的网络验收继续由使用者触发。

安装后至少分别验证 COM 参数适配、HCL 打开/保存隔离工程、原生控制台、WHPX guest 启动与回退。任一项未验证就维持 hcl_runtime_compatible=null；不得把安装完成、sdk 声明相似或备份存在写成实时成功。

原始资产、52 文件备份和私有 VM 哈希清单位于本分支忽略的 work/feasibility/plan-b-20261002/，不能随 Git 分发。不要删除或覆盖旧回执。
