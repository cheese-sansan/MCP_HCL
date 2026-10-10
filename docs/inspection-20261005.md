# 运行态查询软件实现

日期：2026-10-05，Asia/Singapore。8a46 工作区，detached 9963ddc，改动尚未提交。固定上游仍为 61 工具/5 资源，整体 Incomplete。

## 交付

新增 hcl_inspect_ports、hcl_read_vlans、hcl_read_qos。当前注册面为 42 工具/6 资源；默认实时写开关关闭时，三个查询在任何工程/VM/管道 I/O 前拒绝。

运行目标以阶段工程和 bindings 对应关系为起点，随后通过实际 Windows 身份、注册 VM 的 running 状态/UUID/CfgFile、VM 当前挂载的本工程 ConfigDisk、UART HostPipe server 路径，及实际服务进程 PID/owner/startvm UUID 核对。没有猜设备编号、修改 UART/ACL、关闭终端或启动设备。

原生路径只发送五种固定 display 命令；每条要求完整回显/提示符、命令和原始字节哈希匹配。端口/VLAN/QoS 从查询结果解析，不从计划补值。失败及不完整 transcript 进入独立 operation_id 回执目录。一次多设备请求先核对全部目标，再开始发送。

格式依据包括 HCL 自带 VLAN/QoS 帮助的已记录原始哈希，以及 H3C 的 [接口状态命令](https://www.h3c.com/en/d_201211/761370_294551_0.htm)、[QoS 命令](https://www.h3c.com/en/d_202009/1327788_294551_0.htm)、[VLAN 命令](https://www.h3c.com/cn/d_202310/1951040_30005_0.htm)。这些资料提供命令与格式依据，不证明本机固件运行支持。

## 不能据此声明的范围

- CLI physical/protocol up 不等于 HCL 实时电缆连接；linked、peer 与 ports_linked 保持 unknown，only_linked=true 返回 live_cable_inventory_unverified。
- PT 其余端口字段、VLAN 工厂默认/容量和完整 QoS 效果尚未验收，不用猜值填齐。
- 模拟 reader 即使声明 native_channel=true，仍被标为 synthetic_inspection_protocol_only，native_readback_verified=false。
- VM 身份绑定不是 runtime 清理隔离证明；guest、配置、连通性和完整 live gate 不因读回而提升。

## 验证

完整回归 **194 项，193 通过、1 Windows symlink 权限跳过，44.173 秒**，日志 work/inspection-final-regression-20261005.txt。11 项新专项包含 formatter、回读完整性、目标不符、未挂载配置盘、注册 UUID/路径/电源状态不符、模拟来源和真实 Win32 非 VBox 服务进程拒绝；没有发送真实 HCL 命令或启动 guest。

首次全量回归因两处旧发现面断言仍为 39 工具而失败，原日志 work/inspection-regression-20261005.txt 保留。独立更新期待的三个工具名和 42 数量后，发现面专项及新完整回归通过；没有删除发现面验证。

新 wheel：work/wheels-inspection-20261005/mcp_hcl-0.5.0-py3-none-any.whl。SHA256：2998eab16d33c62b80fd285109ef44529e025115ad08e698ebeb2216bd2a4b4f。38 个包文件与源码逐字节一致，42/6 发现面和默认查询拒绝通过。

最新准备包已校验并复制到 C:/Users/Public/Documents/MCP_HCL_Lab_20261005_Inspection。无依赖 wheel、厂商程序、镜像或原用户配置；旧拓扑/规划/控制台包保留。

## 下一步

MCPHCLLab 账号已创建，但本轮仍没有 Win32_UserProfile 记录；用户需首次登录以生成真正的配置目录。之后先完成 runtime 隔离，再用单台设备验证 UUID/配置盘/管道服务进程及实际输出格式。保留所有拒绝与失败，不修改原 ACL/镜像来迁就新 reader。

三个查询上游映射仍 planned；12 implemented / 46 planned / 3 unverified 不变，full_live_gate_passed=false。
