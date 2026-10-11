# API 使用指南

MCP 当前发现 55 工具/6 资源，协议 `contract_version=2`，计划 `schema_version=1`。精确名称、参数和默认值以 `tools/list` 与 [Schema](offline-contracts.json) 为准；类型、错误、恢复和证明边界见 [合同](contract-v2.md)。

## 工具分组

| 分组 | 入口 |
|---|---|
| 项目、目录与能力 | hcl_capabilities、hcl_list_projects、hcl_inspect_project、hcl_list_devices、hcl_get_device_details、hcl_list_modules、hcl_list_templates、hcl_parity_report |
| 规划 | hcl_plan_topology、hcl_estimate_plan、hcl_validate_plan、hcl_explain_plan、hcl_fix_plan |
| 文件产物 | hcl_generate_configs、hcl_generate_operations、hcl_export_artifacts、hcl_load_plan、hcl_stage_copy、hcl_stage_plan、hcl_full_build |
| 阶段编辑 | hcl_stage_add_device、hcl_stage_link、hcl_stage_rename_device、hcl_stage_move_device、hcl_stage_delete_device、hcl_stage_unlink、hcl_stage_add_note、hcl_stage_clear_annotations |
| 后端与 GUI | hcl_bridge_status、hcl_backend_capabilities、hcl_backend_topology、hcl_device_power、hcl_console_exec、hcl_open_project、hcl_save_project |
| 配置与恢复 | hcl_backup_config、hcl_restore_config、hcl_live_deploy、hcl_verify_connectivity、hcl_apply_acl、hcl_remove_acl、hcl_apply_vlan、hcl_apply_vlan_network、hcl_apply_nat、hcl_remove_nat、hcl_apply_interface_tuning、hcl_apply_stp、hcl_apply_port_security、hcl_apply_netstream |
| 观察与审计 | hcl_inspect_ports、hcl_read_vlans、hcl_read_qos、hcl_diff、hcl_health_check、hcl_audit_security |

资源为 `hcl://capabilities` 和 `hcl://catalog/` 下的 devices、ports、aliases、cables、templates。

## 上游 API 对应

`hcl_parity_report.api_compatibility` 对照固定上游 62 工具/5 资源的 Python 声明与当前 MCP 发现结果。每个工具列出上游参数、类型注解、必填性、默认值及返回注解，以及实际注册的 HCL 目标和完整输入 Schema。差异包括参数名、必填性、默认值；`request`/`parameters` 包装中的同名候选另列，不能当成已经实现的转换。

上游声明从哈希匹配的源码经 AST 提取，未导入或执行上游代码；嵌套模型和运行时错误/输出/行为没有由此验证。报告明确保留 `automatic_translation_available=false`，不注册 `pt_*` 别名。`mapped_entry_point` 只表示对应 HCL 入口已注册，仍须使用它的参数和证据边界；未注册目标为 `not_implemented`。阶段替代项限于保存的工程。

例如上游规划参数平铺且 DHCP 默认为 true，HCL 接收严格 `request`、DHCP 默认为 false，当前路由选择没有 EIGRP。上游独立 DHCP Server 没有 HCL 入口。调用者必须明确这些差异，不能只更换工具前缀。资源 URI 对应也不表示两平台目录或能力内容等价。

## 离线流程

1. 配置实际安装/工程根和独立输出根，保持真实写开关为 0。
2. 查询目录和模板，以明确型号、接口与端口映射生成/校验计划。
3. 生成配置或操作意图，导出带哈希的文件，再通过 hcl_load_plan 重载校验。
4. 需要工程副本时使用 stage 工具；源工程不被替换。实时执行清单仍不能以 `executable=false` 当成已运行。

artifact_name/stage_name 使用受限 ASCII 名称，未知字段拒绝。幂等键只允许复用匹配且哈希未变的离线产物；失败和已有占用目标不会被静默覆盖。

## 计划与服务

计划含明确设备/类别、链接、IPv4/IPv6 地址、路由、子接口、DHCP 主机设置和服务。九类模板包括固定上游语义的 star；custom 只接受显式 custom_plan。引用的设备、接口、ACL、VLAN 等必须存在；不根据目录顺序猜真实线缆或端口映射。

服务包括 DHCP、OSPF、RIP、VLAN、ACL、NAT、Security、Wireless、QoS、NetStream。它们是有界生成配置，不代表协议所有选项。服务主要采用 IPv4；基础接口/静态路由可生成 IPv6，具体字段见 Schema。引用、重复项、冲突地址和 CLI token 严格检查。

凭据由调用者明确提供，导出的计划/配置可能包含它们，必须留在本地私有输出根。SSH 生成依赖已有主机密钥。AC 射频启用可明确生成，FAT AP 使用调用者指定 radio_interface；型号/固件兼容和逐端口增强不能由目录存在证明。

Phone 为显式原生无线终端，必须 DHCP；安全关联、PSK 及原生设置的保存/恢复未完成时，完整配置与工程生成仍拒绝。include_configs=false 可记录意图，不是完整生成或运行验收。

## 工程编译和配置事务

hcl_stage_plan 在副本中使用实际型号模板与显式 port_map 编译，保留无关源字段。startup 占位文件不是部署成功，生成的命令文本单独保存。hcl_full_build 默认 activate=false；activate=true 需要 hcl_pid 且拒绝离线 idempotency_key。

阶段编辑重新校验绑定计划并生成对应产物，注释清理只移除已知 NOTE 块。GUI 需要 stage receipt、真实身份和工程 caption；原生配置服务还需 UUID/配置盘/管道绑定、备份及恢复预检。正式执行顺序见 [测试指南](live-acceptance.md)。

捕获模型资料可通过 MCP_HCL_PROFILE_ROOT 提供；引用文件哈希再次核对，不证明厂商默认、物理映射或无线命令接受。命令参考读取包内元数据，verify_offline_reference.py 可只读核对安装资料；资料存在与版本手册不等于 guest 行为通过。
