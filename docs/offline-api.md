# Offline API, contract v2

All calls use actual JSON objects/numbers/booleans. The authoritative input
schemas, including every service parameter and range, are in
[offline-contracts.json](offline-contracts.json). Unknown fields are errors.

## Tool inputs and results

| Tool | Arguments | Result payload |
| --- | --- | --- |
| hcl_list_modules | optional model | documented NIC enhancement mode, fixed profiles and compatibility warnings |
| hcl_list_templates | none | five HCL-native graph templates and source hash |
| hcl_plan_topology | request object | normalized plan, validation, request and source evidence |
| hcl_estimate_plan | same request | device/link/address/route/service counts from the same planner |
| hcl_explain_plan | plan object | deterministic facts and evidence boundaries |
| hcl_fix_plan | plan object | repaired copy, changes and remaining validation errors |
| hcl_generate_configs | plan object | device-ID → Comware command text, source evidence and warnings |
| hcl_generate_operations | plan object, include_configs=true | versioned create/link/annotation/config intents, executable=false |
| hcl_export_artifacts | plan object, artifact_name, optional idempotency_key | atomic directory, file paths, manifest and hashes |
| hcl_load_plan | artifact_directory | hash-checked normalized plan and source_operation_id |

`artifact_name` is 1–20 ASCII letters/digits/underscores, starting with a letter.
Export/load paths are confined to the configured output root. Occupied names are
not overwritten. Stage tools use the same name grammar and optional durable
idempotency key. Unkeyed calls preserve their original refusal on an occupied name.

## Planning request

Defaults: `schema_version=1`, `name="HCL Lab"`, `template="multi_lan"`,
`routers=2`, `switches_per_router=1`, `pcs_per_lan=0`,
`router_model="MSR36-20"`, `switch_model="S5820V2-54QS-GE"`, `host_model="PC"`,
`lan_pool="10.0.0.0/16"`, `transit_pool="172.16.0.0/16"`,
`routing="static"`, `dhcp=false`.

Templates: single_lan (one router), multi_lan (router chain), star/hub_spoke
(central router), three_router_triangle (exactly three routers). Model choices
must be installed; there is no silent substitution. Port exhaustion, device-limit
overflow, invalid template counts and overlapping/exhausted address pools reject
the request. Static routes use deterministic shortest paths to other LANs.
OSPF and RIP emit explicit service intents. Estimation never invents physical
latency, CPU/memory consumption or firmware support.

WAN/cloud, wireless-client request shapes, EIGRP and the remaining upstream
template semantics are not covered by this request schema. They are not silently
ignored or counted as full planner parity.

Repair changes only exact case aliases, unused physical-interface assignments
and a determinable link medium. It preserves user IPs/routes/services, returns
its changes, and revalidates. Unfixable errors remain rejected.

## Service parameter profiles

Each service is `{device, feature, parameters}`. The feature selects one strict
parameter model; the parameters object cannot be missing or contain a typo.

| Feature | Required core fields / variants |
| --- | --- |
| dhcp | mode, interface; server: pool/network/gateway; relay: servers. Optional DNS and excluded ranges. Server subnet/gateway must match the addressed interface. |
| ospf | process_id, router_id, networks[{network,area}]; optional passive_interfaces. IPv4 networks must contain an addressed interface. |
| rip | classful IPv4 networks; version 1/2 and process_id; optional passive_interfaces |
| vlan | vlans; optional access/trunk ports and svis[{vlan,cidr}] |
| acl | number 2000–3999, rules[{id,action,protocol,source,destination,source_port,destination_port}]; optional bindings. Basic ACLs only match sources. |
| nat | nonempty outbound[{interface,acl}] or static[{interface,global_address,local_address,protocol?,global_port?,local_port?}] |
| security | username/password; privilege 0–15, optional vty_acl/vty_last; Telnet disabled. An existing SSH host key is a precondition. |
| wireless | mode, template, ssid, vlan, psk; AC: AP device/name/model/serial ID and radio; FAT AP: caller-supplied radio_interface |
| qos | classifier/behavior/policy, ACL and/or DSCP match, DSCP remark and/or CIR, bindings |
| netstream | IPv4 collector, UDP port, version 5/9, interfaces with direction |

Referenced ACLs, VLANs, devices and physical interfaces must exist in the plan
and installed catalog. SVI references are permitted when explicitly declared.
Duplicate services/rules/ports, conflicting addresses and unsafe CLI tokens are
rejected. Credentials are caller supplied; there is no default real password.
Exported plans/configs can contain those explicit credentials and stay under the
local ignored output root.

These are bounded profiles, not every option of the named protocols. IPv6 base
interface addresses/static routes are generated; these ten service profiles use
the IPv4 forms listed above. No opaque parameters are saved and silently dropped.

## Evidence and activation

Command reference fingerprints come from the installed HCL command help. The
packed metadata includes syntax names/hashes, not vendor manual contents.
`verify_offline_reference.py` compares 28 source records with the installation.
The HCL 5.10.1 user guide documents native NIC enhancement, but does not prove
5.10.3 per-model compatibility. AC/AP image/family discovery does not supply
their missing default CLI configurations. Port-order pairings are explicitly
unverified candidates.

AC radio activation is explicit in generated configuration, following the local
radio-command reference; H3C's
[Comware 7 wireless examples](https://www.h3c.com/en/Support/Resource_Center/EN/Home/Wireless/00-Public/Doc_Sets/Doc_Packages/H3C_Wireless_All-in-One/03/202209/1689567_294551_0.htm)
also distinguish factory configuration and model/version differences. These
references do not verify this machine's guest state.

Operation manifests preserve devices, links, annotations and optionally config
commands. Scene-port candidates are labeled mapping_verified=false and need the
future execution adapter and mapping/GUI acceptance. All runtime, guest,
configuration and connectivity claims remain false.
