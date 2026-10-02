# MCP_HCL Codex 交接

版本 **0.5.0**；分支 `codex/hcl-live-parity`；更新于 2026-10-02。固定上游 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d`，目标仍为 61 工具 / 5 资源的逐项功能等价。总体 completion=incomplete。

## 权限与来源

DSH 的 7 个提交已快进接入，dsh 分支已安全删除；原工作区 E:/MCP_HCL 保持 detached 1200f30，原工程、回执和依赖不改写。DSH 历史与索引位于 docs/history；0.4.0 的 README/HANDOFF 也已归档。

使用者最新批准的是离线实现及独立实验环境准备。本机不得新增启动项、修改 BCD、关闭安全功能、更换共享 VirtualBox、自动启动 guest 或重启。Push、PR、发布不在范围内；超过一分钟的真实验收由使用者触发。实时写开关默认关闭，工程改动仅写副本。

## 启动配置清理事实

使用者单独批准后，2026-10-02 已先导出当前 BCD 并验证备份，再删除 MCP_HCL Lab 和一次性启动设置。正常 Windows、恢复环境和其他 BCD 对象回读不变；未进行开机验证。备份回执位于 C:/Users/w8p1p/Documents/MCP_HCL-boot-backups/20261002-151945-bd06865eed7a4b7ab8f346c7c518c218/，BCD SHA256 为 0514F3230D816A53591C326187EB27E26A423C02BBBAC5C7B3C58E50A2CD0B2F。

活动 hcl_lab_boot.ps1 和 hcl_lab_environment.ps1 已退役为拒绝执行入口。历史原件仅供审计，不能作为操作指南。环境预检不再依赖启动项名称或 GUID；进程存在、Hypervisor 状态和 guest 列表不能证明原生控制台或网络就绪。

## 已交付的软件

- 严格原始 JSON、统一结果信封、参数/计划错误分类、跨进程离线幂等与产物完整性检查。
- 九模板确定性规划、十类服务模型与有资料依据的离线模板、导出重载、双栈与子接口。
- 隔离工程生成与编辑、双端链路同步、GUI 身份门控；39 工具 / 6 资源。
- 持久控制台、独占租约、完整回显/提示符回读、原生配置备份/恢复预检和部署失败恢复适配器。
- 可搬运的 v2 私有型号证据：相对路径清单、模板身份、配置/版本/接口内容核对、Phone 页面与保存差异、原始来源哈希。导入使用持久幂等，重复冲突、篡改、越界和合成来源均拒绝。
- 显式原生无线终端及安全模式；Phone 不使用 Comware CLI，不允许静态地址、未验证 IPv6 或安全降级。原生字段差异不自动升级为已验证语义。
- mcp-hcl-lab：准备、采集、审计、导入、只读预检及使用者触发的有线验收入口。无线验收入口明确拒绝尚不具备的部署能力。

## 验证与完成门槛

当前软件测试、wheel 和验收包哈希见 docs/progress-verification-050.json。真实 stdio 的 Schema 与目录必须从当前工作区读取；本轮已创建独立 .venv。MCP contract_version=2、plan schema_version=1 不变；型号证据 schema_version=2 是另一种合同。

无线阶段仍 Incomplete：AC/AP 本机默认配置缺失、独立端口/射频映射未验收，Phone 的 WPA2-PSK 关联、设置持久化和恢复未取得真实证据。5.10.1 手册只允许未加密 Phone 无线诊断，不能推断 5.10.3 的安全支持。

实时阶段未执行：当前没有独立实验环境；本机仍保留虚拟化冲突阻塞。软件测试和模拟回执不替代 GUI、guest、配置、恢复、路由、DHCP 或 ping 验收。上游计数仍 12 implemented / 46 planned / 3 unverified，仅在每行窄范围 verified_scope 内成立。

## 下一步

按 docs/live-acceptance.md 在独立环境收集真实 AC/AP/Phone 及有线型号证据。先完成型号/映射资料检查，再运行固定三路由器验收；无线只有真实安全关联、两客户端正确 DHCP 与连通性通过才能收口。不得因导入带有成功标志的文件而提升运行结论。每次运行保留独立新回执，恢复失败逐设备报告，不重放原部署。

## 给下一位 Agent：先做独立软件测试

使用者本次要把项目交给另一个 Agent 测试。先验证现有交付，不把测试请求理解为允许更改宿主机启动、安全、虚拟化设置或开展真实部署。

- 当前工作区：`C:/Users/w8p1p/.codex/worktrees/ed66/MCP_HCL`。交接前 HEAD 为 `2cb7f52`，工作区干净；本次后续提交只更新交接文档。接手先重新检查 branch、HEAD 和 status，不自动切换、重置或清理工作区。
- 被验证的代码提交是 `85bcf24919267a99e7d948a006fa5422de9bdd0e`；`2cb7f52` 添加最终验证记录。现有结果为 **138 项，137 通过、1 项 Windows symlink 权限跳过**，耗时 35.245 秒；46 条资料哈希校验通过，pip check 通过。这些是上一轮结果，本次交接未重跑。
- 原始软件日志：`work/050-final-regression.txt`；隔离 wheel 检查：`work/050-wheel-verification.json` 与 `.log`，复现脚本 `work/verify-wheel-050.py`。它使用合成工程，真实 stdio 指 MCP 传输真实启动，不指真实 HCL guest。
- wheel：`work/wheels-050-final/mcp_hcl-0.5.0-py3-none-any.whl`，SHA256 `f15f123c4f409b44a3ea39b5dce6422d593de13079bf687e28f27d69e815b797`。
- 已准备的搬运目录：`work/lab-bundles/Hcl050/`。内含 wheel、依赖锁定清单、固定实验要求和指南；不含依赖 wheel，独立环境首次安装需要包源访问。所有 work/ 产物和 .venv 都不随 Git 搬运；换工作区后先确认文件存在，缺失时在新目录重新生成，不引用不存在的历史回执作为当前证据。

### 安全的软件测试入口

在当前工作区已有独立 .venv 时执行下面的命令。若在另一工作区测试，改为实际路径并建立自己的环境；不要修改 E:/MCP_HCL/.venv，也不要让它的 editable 安装加载旧 DSH 代码。

```powershell
Set-Location 'C:\Users\w8p1p\.codex\worktrees\ed66\MCP_HCL'
git status --short --branch
git rev-parse HEAD
$env:PYTHONPATH = (Join-Path (Get-Location) 'src') + ';' + (Join-Path (Get-Location) 'tests')
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:MCP_HCL_ALLOW_LIVE_WRITE = '0'
# 清除本进程可能继承的私有资料入口，避免回归加载用户资料。
Remove-Item Env:\MCP_HCL_PROFILE_ROOT -ErrorAction SilentlyContinue
$testRun = [Guid]::NewGuid().ToString('N')
$testLog = Join-Path (Get-Location) ('work\agent-test-' + $testRun + '.txt')
.\.venv\Scripts\python.exe -B -X utf8 -c "import mcp_hcl; print(mcp_hcl.__version__, mcp_hcl.__file__)"
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests *> $testLog
$testExit = $LASTEXITCODE
Get-Content -LiteralPath $testLog -Tail 20
if ($testExit -ne 0) { throw "Regression failed; preserve $testLog" }
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -B -X utf8 scripts\verify_offline_reference.py `
  --install-root 'D:\HCL' --output ('work\agent-reference-' + $testRun + '.json')
.\.venv\Scripts\mcp-hcl-lab.exe audit `
  --directory work\lab-bundles\Hcl050 --preparation-bundle
```

缺少 D:/HCL 或搬运产物时，仅运行可满足前提的软件检查，并分别报告缺失项。资料哈希不匹配不可改成跳过后宣称资料验收通过。不要为消除 symlink 权限跳过而改变本机系统设置。

### 测试重点与预期拒绝

- 核对真实 stdio 的 39 工具 / 6 资源、`docs/offline-contracts.json` 以及无线请求的 `$defs` 引用。保持外层参数错误与内部请求/计划业务 rejected 的既有分类，验证未知字段和布尔冒充整数没有被转换。
- 独立覆盖九模板、DHCP/静态与 SVI 冲突、子接口、保留 PSK 意图；检查副本编辑后的双端链接、绑定计划及源文件不变。
- 对证据包做搬运、版本/身份不符、路径越界、重复型号、哈希篡改、合成来源及伪造成功标志测试。导入同键并发、跨进程重试和失败写入必须保持来源与旧产物不变。
- 核对原生采集仅发送三条 display 白名单命令；租约、分页、输出归因及不完整失败回执应使用测试通道验证。软件模拟不得提升 native/runtime 结论。
- `accept-wireless` **预期返回 rejected、退出码 2**；Phone 安全关联和设置序列化缺证据导致完整生成拒绝是当前硬门槛。开放计划的结构可通过，不代表配置、工程或安全无线已完整生成。
- 控制台和部署故障测试覆盖备份不可用、中途失败、断连、恢复所有已修改设备、恢复失败及禁止重放。只使用合成设备/管道；不要为了检查恢复行为而在本机调用真实配置命令。

### 真实验收前置条件与交付报告

当前没有独立 HCL 实验环境。最后的只读环境回执 `work/050-environment.json` 记录 Hypervisor=true、VirtualBox 6.0.14、GUI/Wrapper 未运行、running guests 为空；客户端版本资源读不到，状态 unknown。该回执是历史观察，接手需要时可重新只读预检；未知值与进程存在均不能判为 runtime_ready。

真实 GUI 打开、guest 启动、控制台配置和可能超过一分钟的网络验收须由使用者在独立环境明确触发。步骤及固定门槛只引用 [实时验收指南](docs/live-acceptance.md)，不要使用 docs/history 的旧重启或 BCD 指令，也不要自动运行 `accept-wired` 或开启实时写开关。

测试结束报告：被测提交与解释器来源、通过/失败/跳过数、新日志路径、最小复现、源工程/历史产物是否改变，以及未具备条件的真实门槛。保留首次失败证据；若修复，记录修复提交并用新回执复测，不覆盖旧失败。测试通过不能增加 implemented 数量或修改无线/实时 Incomplete 结论，除非有对应层次的真实证据。

### Suggested skills

- `code-review-and-quality`：需要独立检查具体代码差异或调查测试发现时使用。
- `api-and-interface-design`：检查 Schema、错误分类或接口兼容性时使用。
- `handoff`：测试结束后整理新的交接，引用原始回执并保留尚未验证的门槛。
