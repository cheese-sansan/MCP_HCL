# User-triggered live acceptance (0.4.0)

The script starts no GUI, Wrapper or VM, changes no BCD entry and performs no
reboot. Real HCL guests must already be running in an isolated staged project.
Current evidence still shows Hypervisor enabled; software tests do not satisfy
this gate.

1. Use an independent, already working HCL environment. Do not recreate a lab
   boot entry or change this host's security or virtualization settings. Read-only
   observations do not prove guest or console readiness.
2. Obtain real model templates and independently check CLI-to-scene port maps.
   Generate the fixed request: multi_lan, 3 MSR36-20 routers, 1 switch/router,
   2 PC DHCP clients/LAN, routing=ospf, ospf_process_id=1, dhcp=true.
3. Call `hcl_full_build` with activate=false and explicit source/map inputs.
   Call `hcl_open_project` explicitly with live writes enabled and the actual
   SimwareClient PID. Preserve its verified exact-project GUI identity result
   in a new JSON receipt file.
4. Start the isolated devices manually in HCL. Release their PuTTY/MultiCC
   consoles; do not allow another client to consume the same stream. Obtain
   the actual topology pipe name from HCL's runtime evidence, not from a guess.
5. Trigger the gate yourself from this checkout's installed virtual environment:

```powershell
$env:MCP_HCL_ALLOW_LIVE_WRITE = '1'
$env:MCP_HCL_INSTALL_ROOT = 'D:\HCL'
$env:MCP_HCL_OUTPUT_ROOT = (Join-Path (Get-Location) 'work\staged')
.\.venv\Scripts\python.exe -B -X utf8 scripts\accept_three_router_lab.py `
  --project-directory 'ABSOLUTE_STAGED_PROJECT_DIRECTORY' `
  --topology 'OBSERVED_TOPOLOGY_NAME' `
  --gui-receipt 'ABSOLUTE_NEW_GUI_RECEIPT_JSON'
```

This operation can exceed one minute and writes running configurations and
independent guest backup files. Native backups must read back completely and a
same-baseline native restore must pass on every device before configuration
commands are applied. Startup configuration is not implicitly saved.

The gate checks exact FULL peer sets, remote OSPF routes, six unique client
leases in the expected /24 LAN with the expected gateway, and six ordered
inter-LAN ping checks with five packets and zero loss. Configuration or network
validation failure triggers native restoration of modified devices. Restoration
failure remains unverified with an explicit manual recovery command. Original
configuration commands are not replayed after disconnects.

Private backup configs and raw console transcripts are under
`MCP_HCL_OUTPUT_ROOT/.deployment-receipts/`. Do not commit them. Existing receipts
are preserved; every operation uses a fresh directory. A failed rollback is not
a successful gate. A verified network subgate does not complete wireless parity
or the full 61-tool upstream inventory.

## Wireless evidence preparation

AC/AP interfaces and wireless client association commands are still missing.
Capture actual model/template facts using the read-only-input collector:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 scripts\capture_model_evidence.py `
  --project-directory 'ABSOLUTE_REAL_TEMPLATE_PROJECT' `
  --configuration-file 'ABSOLUTE_CAPTURED_MODEL_CONFIG' `
  --model 'ACTUAL_MODEL_NAME' `
  --output 'work\model-profiles\NEW_MODEL_RECORD.json'
$env:MCP_HCL_PROFILE_ROOT = (Join-Path (Get-Location) 'work\model-profiles')
```

The catalog rechecks both source hashes and model/interface consistency. This
records captured configuration interfaces, not factory defaults or proven scene
mappings. Wireless client command generation remains blocked until a verified
model-specific association profile is implemented and accepted.
