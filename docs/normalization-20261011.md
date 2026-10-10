# 分支整合与代码规范化（2026-10-11）

全部本地来源分支历史及最新已验证工作区成果已纳入本地 main。产品验收仍为 **Incomplete**，`full_live_gate_passed=false`。未 push，来源分支和其他工作区保留。

## 整合与备份

原 main=`1005ac3fb455b69b4cbd07b4eaca4f16a3d94e8c`，codex/hcl-live-parity=`9963ddc559d3f7d9ccecfc5a58f9adbaf2695f62`，dsh-2=`e7231a3b4139219910af2bb84901aedd71bae986`。

在干净工作区先合并两条来源历史，再导入 nat-transactions 的 197 个已逐字节备份文件，包含最新软件修复及原生测试记录。8a46/entry 独有历史和冲突副本另行归档。冲突涉及交接、README、退役脚本、拓扑合同和旧测试；采用最新严格合同，旧分支损坏工程/P0 修复已被当前实现覆盖。dsh 独有旧脚本与证据在 `docs/history/dsh-2-e7231a3/`，不恢复为当前执行入口。

远端只观察到 origin/main=`1005ac3…`。第一次 HTTPS 查询连接重置，HTTP/1.1 只读查询成功；没有写远端。

## 规范化与保持性

109 个既有 Python 文件使用自动 Ruff 格式化/导入整理。除导入排序和说明字符串外，可执行 AST 未变；固件字符串的局部 lambda 改为命名 def。配置固定 UTF-8/LF、4 空格和 100 列软限制，历史文件不格式化。

BudgetConsole、atomic_json、unique_json、operation_json、incomplete_operation 移入 `transactions.py`，主体 AST 保持。NAT 保留原名称兼容导出，其他配置服务直接依赖共用模块。业务状态、调用顺序、错误码、工具签名和证据层次保持。

增加 `scripts/check_all.py`、开发指南、文档索引与决策记录；更新当前 README/HANDOFF/测试计划。历史 JSON、失败回执和旧候选不改写。完整 SDK 工具名称、描述、参数/default/schema 与重构前完全相同，仍为 55 工具/6 资源。

## 验证结果

| 范围 | 执行 | 通过 | 跳过 | 失败/错误 |
|---|---:|---:|---:|---:|
| 整合基线完整软件回归 | 330 | 329 | 1 | 0 / 0 |
| 格式化阶段专项 | 49 | 49 | 0 | 0 / 0 |
| 规范化源码完整回归 | 330 | 329 | 1 | 0 / 0 |
| 新 wheel 受影响专项 | 177 | 176 | 1 | 0 / 0 |

各行包含阶段重复/专项验证，不合计为独立用例总数。跳过项因当前账号无法创建符号链接，其实际拒绝路径不记为通过。

Ruff lint/format 和 pip check 通过。wheel 安装后实际导入来自独立 venv 的 site-packages。

新候选：`C:/Users/Public/Documents/MCP_HCL_Normalized_20261011_ccf9210a/mcp_hcl-0.5.0-py3-none-any.whl`。

SHA256：`2c57afcdf7b0f5234a738a255c5b904e15d52a000e6ab7f5f6aacd6af9e5880a`。57 个包文件与源码逐字节一致；旧 56 文件、SHA `3d3663ca…65f9a` 候选与回执属于重构前版本，仍保留。

软件写开关为 0；默认检查允许已审阅的离线 CLI 和明确的软件 PowerShell 测试模块（Plan/ValidateOnly/解析/退役拒绝），也使用私有合成 named pipe。没有启动厂商程序、访问真实 guest CLI、创建/删除账号或修改宿主。本轮不重复已成功的原生生命周期。

## 证据与接手

证据根：`C:/Users/w8p1p/.codex/worktrees/ddea/MCP_HCL/work/normalization-20261011/ccf9210a95624f7ba9401fbb79e0dead`。

- `all-refs.bundle`、`bundle-verify.txt`：原 refs 的可验证 Git bundle。
- `snapshots/`、`worktrees.json`：五个工作区 tracked/untracked 原字节、HEAD/status 与 SHA。
- `baseline-runs/`、`format-runs/`、`final-runs/`、`candidate-runs/`：独立回执、日志、依赖、逐项结果与 manifest。
- AST/事务助手提取及 `contract-before.json`/`contract-after.json`：保持性证据。
- `source-worktree-preservation.json`：其他四个工作区文件/HEAD 未变；`historical-preservation.json`：34 个既有历史文件未变。
- `delivery.json`：最终 main HEAD、全部原分支 refs 祖先检查、clean 状态与 bundle 复核。

原生生命周期/账号清理以原报告为准；CLI 独占阻塞、配置/startup/流量及完整 61/5 行为等价未决项没有关闭。继续从本地 main 的当前源码与新候选接手，来源工作区作为历史保留。

机器可读记录见 [normalization-20261011.json](normalization-20261011.json)，维护说明见 [development.md](development.md)。
