# HCL Agent 使用指南（当前实现）

先调用 `hcl_capabilities` 和 `hcl_parity_report`。按照每项的状态及 `verified_scope` 判断证据范围。安装资料、计划校验、工程文件生成和设备运行是不同的验收层。

## 型号与接口

`hcl_list_devices` 返回本地 `devicecfgs` 中发现的型号；`hcl_get_device_details(model)` 返回默认接口与固件字符串。默认配置中的版本字符串不能证明当前镜像已启动或接受某条命令。`hcl://catalog/ports` 返回本地 `deviceInfo.ini` 的端口族及索引，不推断每个型号的 CLI 映射。

## 版本化计划

`hcl_validate_plan` 接受一个 `plan` 对象。例如：

```json
{
  "schema_version": 1,
  "name": "两路由器实验",
  "devices": [
    {"id": "r1", "name": "路由器一", "model": "MSR36-20", "x": 0, "y": 0},
    {"id": "r2", "name": "路由器二", "model": "MSR36-20", "x": 200, "y": 0}
  ],
  "links": [{
    "a": {"device": "r1", "interface": "GigabitEthernet0/0"},
    "b": {"device": "r2", "interface": "GigabitEthernet0/0"},
    "medium": "ethernet"
  }],
  "addresses": [
    {"device": "r1", "interface": "GigabitEthernet0/0", "cidr": "10.0.0.1/30"},
    {"device": "r2", "interface": "GigabitEthernet0/0", "cidr": "10.0.0.2/30"}
  ],
  "routes": [],
  "services": [],
  "annotations": [{"text": "隔离实验", "x": 0, "y": 100}]
}
```

计划使用 Comware 接口名称。工程文件中的 `GE_0/0` 等场景端口键属于另一种表示，不能直接混用。当前计划校验会检查已安装默认接口、重复 ID/名称、未知设备、重复占用端口、自连接、线缆类型、重复 IP、IPv4 网络/广播地址以及路由地址族。

`services` 可保存 DHCP、OSPF、RIP、VLAN、ACL、NAT、安全、无线、QoS、NetStream 意图，但目前不会生成或执行配置；参数未做完整的协议校验，结果会显式报告 `feature_runtime_unverified`。`valid: true` 仅表示已实现的结构与语义检查通过，不能解释为服务配置或网络已可用。导入导出、一键构建、完整 Comware 生成和实时下发尚待完成。

## 现有工程操作

用 `hcl_inspect_project` 读取源工程。用 `hcl_stage_copy`、`hcl_stage_add_device`、`hcl_stage_link` 生成独立工程副本。`status: staged` 只证明保存文件层面的结果；仍须确认画布和运行态。

本机实时门槛已证明隔离副本打开/保存、设备新增及链路增删。设备启动失败、设备删除未完成、CLI 未回读；这些步骤不能由离线计划校验代替。耗时超过一分钟的设备或连通性验收由使用者触发并保留回执。已有成功回执可沿用，仅对新增逻辑、具体风险及尚未完成的必需门槛追加验证。
