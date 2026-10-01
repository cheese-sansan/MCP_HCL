# MCP contract v2 (0.2.0)

All tool calls validate their original JSON arguments before the MCP SDK can
coerce or pre-parse them. Unknown keys, numeric strings, boolean integers,
nonfinite numbers and JSON encoded inside strings are rejected. JSON numbers
remain accepted for coordinates. Nested plans have strict structure and types.

Every tool result includes `contract_version=2`, `status`, `operation_id`,
`request_id` (the MCP request), `target`, `verified_scope`, `evidence`,
`errors[{code,message,path?}]`, `warnings`, `runtime_verified` and
`full_live_gate_passed`. Existing business payload keys are retained.
Backend wire IDs are `backend_request_id` and remain in protocol evidence.

Invalid tool arguments and unknown tools set MCP `isError=true`. Plan validation
and project business rejections use `isError=false` and `status=rejected`.
`verified` and `accepted` are meaningful only within `verified_scope`.

Stage tools accept optional `idempotency_key`. Successful retries persist in the
output root's `.operations.sqlite3`. Same key and input return the same
operation and hash-verified artifacts with `replayed=true`. A different tool,
input or source contents produces `idempotency_conflict`; missing or changed
output produces `artifact_changed`. The current MCP request ID is fresh on each
retry. Existing unkeyed behavior still refuses an occupied stage name.
Failed writes do not reserve the key. Live control never uses this replay path.

`hcl_lab_environment.ps1` now requires `-EntryId` or `-CreateReceipt` in addition
to `-ReceiptDirectory`. Only a verified Create receipt is accepted. Unknown or
failed BCD/Hypervisor readings cannot pass the environment gate. This change
does not perform any BCD writes or reboot.

P0 verification on 2026-10-01: 70 tests run, 69 passed and one symlink test
skipped for missing Windows privilege. Receipt: `work/p0-tests-final.txt`.
