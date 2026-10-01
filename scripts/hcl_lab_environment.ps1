# Post-reboot verification for the MCP_HCL Lab boot entry.
#
# Run this AFTER manually restarting and selecting
# "MCP_HCL Lab (Hypervisor and VSM off)". It is read-only:
# it changes no boot settings and starts nothing.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\hcl_lab_environment.ps1 `
#     -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001

param([Parameter(Mandatory = $true)][string]$ReceiptDirectory, [string]$EntryId, [string]$CreateReceipt)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'hcl_lab_verdict.ps1')
$expectedEntry = $EntryId
if ($CreateReceipt) {
    if ($EntryId) { throw 'Supply EntryId or CreateReceipt, not both.' }
    $creation = Get-Content -LiteralPath $CreateReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($creation.action -ne 'Create' -or $creation.status -ne 'verified') { throw 'A verified Create receipt is required.' }
    $expectedEntry = $creation.entry_id
}
if ($expectedEntry -notmatch '^\{[0-9a-fA-F-]{36}\}$') { throw 'Supply the explicit lab EntryId or its verified CreateReceipt.' }
$result = [ordered]@{
    operation_id = [Guid]::NewGuid().ToString('N')
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    checked_at = (Get-Date).ToString('s')
    expected_lab_entry = $expectedEntry
    booted_lab_entry = $false
    hypervisor_present = $null
    device_guard = $null
    bcd_current = $null
    bcd_current_read_ok = $false
    verdict = 'unknown'
    next_step = $null
    error = $null
}

try {
    # 1. Which entry did we actually boot? bcdedit's {current} is the running one.
    $bcd = & "$env:SystemRoot\System32\bcdedit.exe" /enum '{current}' /v 2>&1
    $result.bcd_current_read_ok = ($LASTEXITCODE -eq 0)
    $result.bcd_current = ($bcd | Out-String).Trim()
    $result.booted_lab_entry = $result.bcd_current_read_ok -and
                               ($result.bcd_current -match [regex]::Escape($expectedEntry)) -and
                               ($result.bcd_current -match '(?im)^hypervisorlaunchtype\s+Off\s*$') -and
                               ($result.bcd_current -match '(?im)^vsmlaunchtype\s+Off\s*$')

    # 2. Is a hypervisor actually present in this session?
    try {
        $info = Get-ComputerInfo -Property HyperVisorPresent, DeviceGuardVirtualizationBasedSecurityStatus,
                                 HyperVRequirementVirtualizationFirmwareEnabled -ErrorAction Stop
        $result.hypervisor_present = $info.HyperVisorPresent
        $result.device_guard = $info.DeviceGuardVirtualizationBasedSecurityStatus
    } catch {
        $result.error = "Get-ComputerInfo failed: $($_.Exception.Message)"
    }

    # 3. Did VirtualBox come up cleanly? VBoxManage is read-only here.
    $vbox = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
    if (Test-Path -LiteralPath $vbox) {
        $vmList = & $vbox list vms 2>&1 | Out-String
        $result.vboxmanage_read_ok = ($LASTEXITCODE -eq 0)
        $result.vboxmanage_vm_count = ([regex]::Matches($vmList, '(?m)^"')).Count
    } else {
        $result.vboxmanage_read_ok = $false
    }

    $result.verdict = Get-HclLabVerdict $result.bcd_current_read_ok $result.booted_lab_entry $result.hypervisor_present
    if ($result.verdict -eq 'unknown') {
        $result.next_step = 'Environment readings failed or are unknown; do not start the live gate.'
    } elseif (-not $result.booted_lab_entry) {
        $result.verdict = 'not_booted_into_lab_entry'
        $result.next_step = 'Restart and select "MCP_HCL Lab (Hypervisor and VSM off)"; nothing else was changed.'
    } elseif ($result.hypervisor_present) {
        $result.verdict = 'lab_entry_active_but_hypervisor_still_present'
        $result.next_step = 'Investigate: the lab entry disabled hypervisorlaunchtype/vsmlaunchtype but a hypervisor is still reported.'
    } else {
        $result.verdict = 'lab_entry_active_and_no_hypervisor'
        $result.next_step = 'Run the remaining live gate: start one isolated HCL device and read its console pipe. Do not rerun already-passed topology steps.'
    }
} catch {
    $result.verdict = 'error'
    $result.error = $_.Exception.Message
} finally {
    $directory = [IO.Path]::GetFullPath($ReceiptDirectory)
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $runDirectory = Join-Path $directory ([Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $runDirectory | Out-Null
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $runDirectory 'lab-environment.json') -Encoding UTF8
    Write-Output "verdict=$($result.verdict) hypervisor_present=$($result.hypervisor_present) booted_lab_entry=$($result.booted_lab_entry)"
    Write-Output "receipt=$(Join-Path $runDirectory 'lab-environment.json')"
}
