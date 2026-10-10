"""Independent acceptance inventory; never derive expected names from the server."""

TOOLS = frozenset(
    """
hcl_capabilities hcl_list_projects hcl_inspect_project hcl_stage_add_device
hcl_stage_link hcl_stage_copy hcl_parity_report hcl_bridge_status hcl_list_devices
hcl_get_device_details hcl_validate_plan hcl_backend_capabilities hcl_backend_topology
hcl_device_power hcl_console_exec hcl_list_modules hcl_list_templates hcl_plan_topology
hcl_estimate_plan hcl_explain_plan hcl_fix_plan hcl_generate_configs hcl_generate_operations
hcl_export_artifacts hcl_load_plan hcl_stage_plan hcl_open_project hcl_save_project hcl_full_build
hcl_stage_rename_device hcl_stage_move_device hcl_stage_delete_device hcl_stage_unlink
hcl_stage_add_note hcl_stage_clear_annotations hcl_backup_config hcl_restore_config
hcl_live_deploy hcl_verify_connectivity hcl_inspect_ports hcl_read_vlans hcl_read_qos
hcl_apply_acl hcl_apply_vlan hcl_apply_vlan_network hcl_remove_acl hcl_apply_nat
hcl_remove_nat hcl_apply_interface_tuning hcl_apply_stp hcl_apply_port_security
hcl_diff hcl_health_check hcl_audit_security hcl_apply_netstream
""".split()
)
RESOURCES = frozenset(
    "hcl://" + name
    for name in (
        "capabilities",
        "catalog/devices",
        "catalog/ports",
        "catalog/aliases",
        "catalog/cables",
        "catalog/templates",
    )
)
assert len(TOOLS) == 55 and len(RESOURCES) == 6
