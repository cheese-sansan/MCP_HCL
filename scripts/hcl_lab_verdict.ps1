function Get-HclLabVerdict {
    param([bool]$BcdReadOk, [bool]$BootedLabEntry, $HypervisorPresent)
    if (-not $BcdReadOk -or $null -eq $HypervisorPresent -or $HypervisorPresent -isnot [bool]) { return 'unknown' }
    if (-not $BootedLabEntry) { return 'not_booted_into_lab_entry' }
    if ($HypervisorPresent) { return 'lab_entry_active_but_hypervisor_still_present' }
    return 'lab_entry_active_and_no_hypervisor'
}
