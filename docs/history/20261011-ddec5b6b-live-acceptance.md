# 0.5.0：独立实验环境验收

本机实验启动项已删除；不能按历史指南重建启动项、修改 BCD 或降低本机系统安全配置。当前没有可用独立环境，真实验收尚未执行。

# Independent HCL lab bundle

This package does not install HCL, start guests, modify Windows boot/security
settings or change shared VirtualBox. Use a separate, already working Windows
HCL environment. Vendor binaries, disks and complete manuals are not included.

1. Create a local venv with Python 3.11+ and install the tested dependencies:
   `python -m pip install -r requirements-tested.txt`
   `python -m pip install --no-deps wheels/mcp_hcl-0.5.0-py3-none-any.whl`
2. Run `mcp-hcl-lab preflight --installation ACTUAL_HCL_DIRECTORY`.
   This is observation only, not a pass for a real guest/console.
3. Manually prepare real model templates and start the isolated guests in HCL.
   Save complete native configs, display version/interface output and independent
   port mapping observations. For Phone save original before/after project files
   and native configuration pages; do not invent Comware interface commands.
4. Fill a capture spec from capture-spec.example.json, then run:
   `mcp-hcl-lab collect --spec PRIVATE_CAPTURE_SPEC --output NEW_PRIVATE_DIRECTORY`
   Manual file collection never sends commands. For native read-only collection,
   explicitly set native_readbacks=true, the observed topology and an exact-project
   verified GUI identity receipt; release PuTTY/MultiCC first. Only display
   current-configuration, display version and display interface are sent.
5. Copy that private directory to the analysis machine; run:
   `mcp-hcl-lab audit --directory COPIED_EVIDENCE_DIRECTORY`
   `mcp-hcl-lab import --directory COPIED_EVIDENCE_DIRECTORY --output-root PRIVATE_PROFILES --name NEW_NAME --idempotency-key UNIQUE_KEY`
   Set MCP_HCL_PROFILE_ROOT to PRIVATE_PROFILES. Integrity does not establish
   factory defaults, runtime acceptance or an independently verified port map.
6. Build the wired request through hcl_full_build(activate=false) with a real
   source project and explicit independently checked port map. Open its staged
   copy through hcl_open_project and preserve the GUI identity receipt. Start
   devices manually and release all other console clients. Only then explicitly
   enable MCP_HCL_ALLOW_LIVE_WRITE and run:
   `mcp-hcl-lab accept-wired --project-directory STAGED_PROJECT --topology OBSERVED_TOPOLOGY --gui-receipt GUI_JSON --installation HCL_ROOT --output-root STAGE_ROOT`
   The gate may exceed one minute. It preflights every native backup/restore,
   writes running config only, and recovers modified devices on configuration
   or network failure. Startup config is not implicitly saved. Failed recovery
   is reported per device with a manual recovery command, never as success.
7. Wireless-test.json describes a separate five-device experiment, not a working
   plan. Open Wi-Fi cannot close its security gate. `accept-wireless` currently
   refuses deployment until Phone secure association serialization and recovery
   are independently established. Never substitute a wired host, AP client-mode
   CLI or open network for the intended secure Phone association.

All operations use new private receipt directories. Keep raw configurations,
PSKs, screenshots and transcripts private. Preserve failed receipts. Imports
retain the original execution host/method and do not claim local execution.

## 在当前工作区准备

```powershell
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir work\wheels-050
.\.venv\Scripts\mcp-hcl-lab.exe prepare `
  --wheel work\wheels-050\mcp_hcl-0.5.0-py3-none-any.whl `
  --output-root work\lab-bundles --name Hcl050 --idempotency-key prepare-050
.\.venv\Scripts\mcp-hcl-lab.exe audit `
  --directory work\lab-bundles\Hcl050 --preparation-bundle
```

搬运整个准备目录。它包含 HCL MCP wheel 和经过测试的完整依赖锁定清单，不包含依赖 wheel，因此首次安装需要独立环境能够访问 Python 包源。准备和导入同键同输入返回原操作；异输入、文件被修改或缺失明确拒绝。默认不覆盖已有目录。

## 型号资料要求

采集清单逐型号指定实际 resourceName 与 control_kind。Comware 模型使用完整配置文件、display version 和 display interface 输出；Phone 使用原生配置页及真实工程保存前后文件。多台同型号只选择一个明确样本，禁止重复型号配置互相覆盖。

原生控制台采集需要显式 native_readbacks=true、实际 topology 和精确工程 GUI 身份回执；它只发送三条白名单 display 命令，没有启动、save 或配置命令。分页、提示符或归因失败停止采集，保留 capture-failed.json 与原始不完整回读，不生成有效型号清单。

证据 schema_version=2 与 plan schema_version=1 相互独立。导入校验相对文件清单、原始哈希、模板设备 ID、配置接口和固件/HCL 版本。它保留原采集主机与方式，运行字段始终 false；原始截图、观察说明和手工成功声明不自动证明端口语义、安全能力或网络成功。

## 正式验收门槛

有线固定 3 台 MSR36-20、3 台 S5820V2-54QS-GE、每 LAN 2 台 PC DHCP 客户端。三路由器线性互联 /30，LAN /24，OSPF process 1 area 0。要求四条方向性 FULL 邻居、正确远端 OSPF LAN 路由、六个唯一租约及网关、三个 LAN 两两双向 ping 各五包零丢包。

无线固定 1 AC、1 AP、1 交换机和 2 Phone。管理 VLAN 1 与业务 VLAN 10 分离，AC 提供网关与 DHCP；AP 型号/序列号、端口和射频必须取自实际资料。开放 Wi-Fi 仅诊断。安全用例要求真实 WPA2-PSK 关联、两个唯一正确租约与双向五包零丢包。Phone 的原生设置持久化与恢复目前未验证，因此 accept-wireless 拒绝下发，而不是调用有线替代或返回模拟成功。

运行配置部署必须先完成所有参与设备的原生备份、完整回读和恢复预检。任何中途失败停止后续下发并恢复本次修改设备；恢复失败报告设备和人工入口，不报告回滚成功。Phone 没有原生配置恢复合同，不能跳过其门槛后宣称无线部署安全。
