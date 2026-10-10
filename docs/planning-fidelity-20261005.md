# 固定上游规划语义修复

日期：2026-10-05，Asia/Singapore。当前修改位于 8a46 独立工作区，基于 detached 9963ddc；没有提交、推送或改变其他分支。完整目标仍是固定上游 61 工具/5 资源。

## 依据与已实现行为

GitHub 连接器读取了固定 `846db381bc2c6ee0229d56e1d7ce8847eb6b213d` 的 [请求模型](https://github.com/Mats2208/MCP-Packet-Tracer/blob/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/models/requests.py)与[规划器](https://github.com/Mats2208/MCP-Packet-Tracer/blob/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/domain/services/orchestrator.py)。本轮实现按照其可观察分配规则适配 HCL，不执行上游代码。

- PC/laptop 数量接受整数或按路由器 LAN 的列表；短列表重复最后一项，空列表分别使用 3/0，未使用的尾项不增加设备。
- PC/laptop 使用各路由器的首个接入交换机，次级交换机不再倍增主机数量。估算直接使用同一规划结果。
- 单臂路由支持 vlans=0 的默认组数，编号改为 10、20…；有 PC 时不生成超过 PC 数量的 VLAN 组。
- PC、laptop、server 使用不同坐标行；宽布局分行以满足当前工程编译器的坐标限制。这不是实时视觉验收。
- 缺少默认主机型号时返回明确业务拒绝，不再泄漏为 internal_error。
- hcl_plan_topology、hcl_estimate_plan、hcl_full_build 的实际 Schema 和离线快照已同步。

`routers=2, switches_per_router=2, pcs_per_lan=3` 的 PC 数量由原实现的 12 修正为 6。旧显式计划与历史工程/幂等结果保留；本轮没有覆盖旧回执。

## 证据与测试范围

完整回归 **171 项，170 通过、1 个 Windows 符号链接权限跳过，47.943 秒**。新规划专项覆盖不均匀数量、短/空/超长列表、非法类型、零群组、次级交换机、VLAN 组数及编号、布局边界和主机型号缺失。

真实 MCP stdio 测试核对数组 Schema 与严格类型，并通过“不均匀 PC 请求 → 独立工程构建 → 计划和 DHCP 命令文件回读”，证明生成 5 台设备、4 条链路、仅一个正确绑定的客户端，源合成工程逐文件不变。这些设备是合成测试对象，未启动 HCL 或 guest。

首个专项失败暴露了缺少 PC 型号时的字典访问错误，记录于 work/planning-fidelity-first-failure-20261005.json。构建链的首次测试夹具缺少新增设备元数据，产品正确拒绝；失败日志 work/planning-fidelity-build-chain-20261005.txt 保留。补齐夹具后的新日志使用独立名称。

当前完整回归日志：work/planning-fidelity-regression-20261005.txt。Schema 快照：docs/offline-contracts.json。源码与上游 blob 指纹、wheel 回执见 docs/planning-fidelity-verification-20261005.json。

## 软件交付

新 wheel：work/wheels-planning-fidelity-20261005/mcp_hcl-0.5.0-py3-none-any.whl。

SHA256：`535eedb0499d7181c1d578a5ef8179f9a4245d61eb9602dadafc232b133a64f5`。

从新 wheel 导入而非 editable 源码后，35 个包文件与当前源码逐字节一致，39 工具/6 资源发现面和不均匀规划通过。包未包含 .net、配置、镜像或厂商程序。新准备包为 work/lab-planning-packets-20261005/MCPHCLLabPlanning，清单哈希已通过，不包含依赖 wheel。

上一轮控制台 wheel 和 MCPHCLLab 准备包继续作为历史资产保留；它们绑定上一轮源码，不代表此轮规划修复。没有发布任何版本。

## 尚未完成

工具映射仍为 12 implemented / 46 planned / 3 unverified，完整上游规划能力仍未声明 implemented。无线原生设置、安全关联、型号资料，以及运行时隔离、真实 CLI/配置/网络闭环依然未通过；此次没有提升这些层次。

本机 MCPHCLLab 账号仍只是审阅方案，未获创建指令、未创建。full_live_gate_passed=false。
