# 上游功能对照表

固定上游提交：`846db381bc2c6ee0229d56e1d7ce8847eb6b213d`。清单从该提交的注册代码提取，共 61 个工具、5 个资源。

该表记录实现状态。计划中的工具名称不代表当前 MCP 已注册；阶段工程替代项只提供保存文件层面的能力。实时门槛及操作回读完成前，运行态功能保留未完成状态。

> 状态按"能否做成"重新分类的版本（离线 / 后端控制平面 / 需要已启动 guest / 无原生等价）见 [路线图](roadmap.md) §5。完成度应以那张表为准：**14 项不需要实时能力，其中 11 项仍未实现**，它们不受设备启动阻塞影响。

| 上游工具 | HCL 目标接口 | 状态 |
| --- | --- | --- |
| `pt_add_device` | `hcl_add_device` | 待实现 |
| `pt_add_link` | `hcl_add_link` | 待实现 |
| `pt_add_module` | `hcl_add_module` | 待实现 |
| `pt_add_note` | `hcl_add_note` | 待实现 |
| `pt_apply_acl` | `hcl_apply_acl` | 待实现 |
| `pt_apply_acl_object` | `hcl_apply_acl` | 待实现 |
| `pt_apply_hardening` | `hcl_apply_hardening` | 待实现 |
| `pt_apply_interface_tuning` | `hcl_apply_interface_tuning` | 待实现 |
| `pt_apply_nat` | `hcl_apply_nat` | 待实现 |
| `pt_apply_netflow` | `hcl_apply_netstream` | 待实现 |
| `pt_apply_port_security` | `hcl_apply_port_security` | 待实现 |
| `pt_apply_stp` | `hcl_apply_stp` | 待实现 |
| `pt_apply_vlan` | `hcl_apply_vlan` | 待实现 |
| `pt_audit_security` | `hcl_audit_security` | 待实现 |
| `pt_backup_config` | `hcl_backup_config` | 待实现 |
| `pt_bridge_status` | `hcl_bridge_status` | 已实现 |
| `pt_clear_annotations` | `hcl_clear_annotations` | 待实现 |
| `pt_delete_device` | `hcl_delete_device` | 待实现 |
| `pt_delete_link` | `hcl_delete_link` | 待实现 |
| `pt_deploy` | `hcl_deploy` | 待实现 |
| `pt_device_power` | `hcl_device_power` | 待实现 |
| `pt_diff` | `hcl_diff` | 待实现 |
| `pt_estimate_plan` | `hcl_estimate_plan` | 待实现 |
| `pt_explain_plan` | `hcl_explain_plan` | 待实现 |
| `pt_export` | `hcl_export_artifacts` | 待实现 |
| `pt_export_topology` | `hcl_export_topology` | 待实现 |
| `pt_fix_plan` | `hcl_fix_plan` | 待实现 |
| `pt_full_build` | `hcl_full_build` | 待实现 |
| `pt_generate_configs` | `hcl_generate_configs` | 待实现 |
| `pt_generate_script` | `hcl_generate_operations` | 待实现 |
| `pt_get_device_details` | `hcl_get_device_details` | 已实现（默认固件与接口，运行态未验证） |
| `pt_health_check` | `hcl_health_check` | 待实现 |
| `pt_inspect_ports` | `hcl_inspect_ports` | 待实现 |
| `pt_install_modules_batch` | `hcl_install_modules_batch` | 待实现 |
| `pt_list_devices` | `hcl_list_devices` | 已实现（本机安装资料） |
| `pt_list_modules` | `hcl_list_modules` | 待实现 |
| `pt_list_projects` | `hcl_list_projects` | 已实现 |
| `pt_list_templates` | `hcl_list_templates` | 待实现 |
| `pt_live_deploy` | `hcl_live_deploy` | 待实现 |
| `pt_load_project` | `hcl_load_plan` | 待实现 |
| `pt_move_device` | `hcl_move_device` | 待实现 |
| `pt_open_project` | `hcl_open_project` | 待实现 |
| `pt_plan_topology` | `hcl_plan_topology` | 待实现 |
| `pt_project_metadata` | `hcl_project_metadata` | 待实现 |
| `pt_query_topology` | `hcl_query_topology` | 待实现 |
| `pt_read_packet_trace` | `hcl_read_capture` | 原生等价性未验证 |
| `pt_read_qos` | `hcl_read_qos` | 待实现 |
| `pt_read_vlans` | `hcl_read_vlans` | 待实现 |
| `pt_remove_acl` | `hcl_remove_acl` | 待实现 |
| `pt_remove_acl_object` | `hcl_remove_acl` | 待实现 |
| `pt_remove_nat` | `hcl_remove_nat` | 待实现 |
| `pt_rename_device` | `hcl_rename_device` | 待实现 |
| `pt_save_project` | `hcl_save_project` | 待实现 |
| `pt_screenshot` | `hcl_screenshot` | 待实现 |
| `pt_send_raw` | `hcl_exec_cli` | 待实现 |
| `pt_set_port` | `hcl_set_port` | 待实现 |
| `pt_simulation_mode` | `hcl_capture_start`, `hcl_capture_stop` | 原生等价性未验证 |
| `pt_simulation_step` | 尚无已验证目标接口 | 原生等价性未验证 |
| `pt_validate_plan` | `hcl_validate_plan` | 部分实现（结构、端口及地址；服务参数待补齐） |
| `pt_verify_connectivity` | `hcl_verify_connectivity` | 待实现 |
| `pt_workspace_options` | `hcl_workspace_options` | 待实现 |

## 平台差异

* `.pkt` 对应 HCL `.net` 工程；配置生成改用 Comware。
* ACL object 接口的目标是相同 ACL 配置效果，需通过 CLI 回读验证。
* NetFlow 的目标对应 NetStream，按固件支持情况验证。
* 抓包与逐事件仿真分别验收；捕获帧不能证明回退或逐 OSI 层决策日志存在。

## MCP 资源

| 上游资源 | HCL 目标 | 状态 |
| --- | --- | --- |
| `pt://capabilities` | `hcl://capabilities` | 已实现 |
| `pt://catalog/aliases` | `hcl://catalog/aliases` | 待实现 |
| `pt://catalog/cables` | `hcl://catalog/cables` | 待实现 |
| `pt://catalog/devices` | `hcl://catalog/devices` | 已实现（本机安装资料） |
| `pt://catalog/templates` | `hcl://catalog/templates` | 待实现 |

## 来源

[工具注册代码](https://github.com/Mats2208/MCP-Packet-Tracer/blob/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/adapters/mcp/tool_registry.py)
[资源注册代码](https://github.com/Mats2208/MCP-Packet-Tracer/blob/846db381bc2c6ee0229d56e1d7ce8847eb6b213d/src/packet_tracer_mcp/adapters/mcp/resource_registry.py)

完整机器可读清单位于 `src/mcp_hcl/data/upstream_parity.json`，包含原始文件 SHA-256 和每项平台说明。上游采用 MIT 许可证；当前清单提取接口名称与映射，未移植上游运行代码。

HCL 另提供 `hcl://catalog/ports`，来自本机 `deviceInfo.ini`。端口族索引不代表所有型号的 CLI 映射。当前目录读取 8 个默认配置型号、11 个端口族；服务命令支持必须待设备启动后实测。
