# Post-reboot verification for the MCP_HCL Lab boot entry.
#
# Run this AFTER manually restarting and selecting
# "MCP_HCL Lab (Hypervisor and VSM off)". It is read-only:
# it changes no boot settings and starts nothing.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\hcl_lab_environment.ps1 `
#     -ReceiptDirectory E:\MCP_HCL\work\feasibility\lab_boot_20261001

param([Parameter(Mandatory = $true)][string]$ReceiptDirectory)

$ErrorActionPreference = 'Continue'
$expectedEntry = '{1031110f-89bd-11f0-ad29-c0bfbeee1ce7}'   # from the Create receipt
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
    $bcd = & "$env:SystemRoot\System32\bcdedit.exe" /enum '{current}' 2>&1
    $result.bcd_current_read_ok = ($LASTEXITCODE -eq 0)
    $result.bcd_current = ($bcd | Out-String).Trim()
    $result.booted_lab_entry = ($result.bcd_current -match 'MCP_HCL Lab \(Hypervisor and VSM off\)') -and
                               ($result.bcd_current -match '(?im)^hypervisorlaunchtype\s+Off\s*$')

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

    if (-not $result.booted_lab_entry) {
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
