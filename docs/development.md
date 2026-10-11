# 开发与检查约定

## 结构与边界

`src/mcp_hcl/` 包含 MCP 注册、严格 DTO、离线工程与各功能服务。`transactions.py` 负责共用交换预算、原子 JSON、历史记录读取和未验证结果；功能模块负责自己的身份、命令差异、回读与恢复。原 `nat_policy` 的助手导入保留兼容别名。

`tests/` 的工具清单独立于生产注册表；模拟依赖不能产生原生验收标志。`scripts/` 放维护入口，`docs/` 放当前合同和具名记录。不得把配置、磁盘、账号凭据或运行时回执加入源码目录。

本次重构保留 55 工具/6 资源的完整 SDK 声明、默认参数、错误码、门控与证据层次；固定上游目标仍为 62/5。`full_live_gate_passed=false` 不能由软件测试提升。

## 风格

Python 3.11+，UTF-8、LF、4 空格、Ruff 100 列软限制。采用明确语句和排序导入，避免一行放多个控制语句。公开模块名及工具签名保持稳定；只为实际复用抽取助手。历史证据保存在私有目录和仓库外备份中；当前 docs 仅放维护所需指南与 Schema。

Ruff 规则与例外在 `pyproject.toml`，编辑器约定在 `.editorconfig`。运行器有意先绑定实际导入来源再导入产品包，其 E402 例外已限定到该文件。

## 安装与验证

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe scripts\check_all.py
```

`check_all.py` 先运行 Ruff lint/format 检查，再执行全部软件测试；只检查格式，不自动改文件。每轮创建新回执目录，保存逐文件 SHA、依赖、实际导入来源、逐项及子用例结果。

检查强制父进程和 SDK 子进程的真实写开关为 0。新增事务中的未注入采集/API/管道调用会失败；进程审计只允许软件 MCP server、已审阅的离线证据 CLI，以及四个明确的 PowerShell 软件测试模块。它们检查 Plan、ValidateOnly、解析或退役拒绝，不启动 HCL/guest、不创建或删除账号，也不修改宿主配置。既有 named pipe 测试使用私有合成服务。

需要修正格式时，单独执行并审阅差异：

```powershell
.\.venv\Scripts\python.exe -m ruff check --fix --select I,E401 src tests scripts
.\.venv\Scripts\python.exe -m ruff format src tests scripts
```

原生生命周期、CLI、配置和流量测试按统一测试计划执行，不能放入默认软件检查。网络发布、push、分支删除和宿主动作各自需要对应授权。

GitHub Actions 的 Software checks 在 main push、PR 和手动触发时使用 Windows/Python 3.12 运行同一软件检查，并构建 wheel、保存回执。执行动作按 SHA 固定、仓库权限仅 contents:read；不安装 HCL/VirtualBox 或进行原生验收。

## 上游声明快照

`data/upstream_contracts.json` 保存固定上游的参数声明；`api_compatibility.py` 校验快照字节 SHA、上游版本、源文件 SHA 和完整清单，再与当前 MCP discovery 比较。维护时使用 `scripts/capture_upstream_contracts.py`，提供原始 tool/resource registry、`upstream_parity.json` 与输出路径。源文件字节必须匹配库存中的 SHA；脚本仅解析 AST，不运行注册器、默认表达式或函数体。

刷新快照后核对独立具名参数用例及 62/5 覆盖，更新校验常量，再运行 SDK 对照测试。未知输出、错误、嵌套类型和原生行为仍须明确标记；声明快照不能替代模型 Schema 或行为验收。
