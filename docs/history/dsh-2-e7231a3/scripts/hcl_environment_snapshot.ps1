param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$repoWork = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\work'))
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $destination.StartsWith($repoWork + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Receipt directory must be below repository work.'
}
$cursor = $destination
while ($cursor.Length -ge $repoWork.Length) {
    if (Test-Path -LiteralPath $cursor) {
        if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'Receipt paths cannot contain reparse points.'
        }
    }
    $cursor = Split-Path -Parent $cursor
}
$runId = [Guid]::NewGuid().ToString('N')
$runDirectory = Join-Path $destination $runId
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$receipt = [ordered]@{
    operation_id = $runId
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    status = 'partial'
    scope = 'read_only_environment_snapshot'
    changes_applied = $false
    full_live_gate_passed = $false
    errors = @()
}
function Observe([string]$Name, [scriptblock]$Read) {
    try { $receipt[$Name] = & $Read }
    catch { $receipt.errors += "$Name : $($_.Exception.Message)" }
}
Observe 'os' { Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber }
Observe 'hypervisor_present' { (Get-CimInstance Win32_ComputerSystem).HypervisorPresent }
Observe 'device_guard' {
    Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard |
        Select-Object VirtualizationBasedSecurityStatus,SecurityServicesConfigured,SecurityServicesRunning
}
Observe 'virtualbox' { Get-ItemProperty 'HKLM:\SOFTWARE\Oracle\VirtualBox' | Select-Object InstallDir,Version }
Observe 'secure_boot' { Confirm-SecureBootUEFI }
Observe 'system_drive_encryption' {
    Get-BitLockerVolume -MountPoint $env:SystemDrive |
        Select-Object MountPoint,VolumeStatus,ProtectionStatus,EncryptionPercentage
}
Observe 'bcd_current' {
    $lines = & "$env:SystemRoot\System32\bcdedit.exe" /enum '{current}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($lines -join "`n") }
    $lines -join "`n"
}
Observe 'bcd_boot_manager' {
    $lines = & "$env:SystemRoot\System32\bcdedit.exe" /enum '{bootmgr}' 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($lines -join "`n") }
    $lines -join "`n"
}
Observe 'optional_features' {
    Get-WindowsOptionalFeature -Online |
        Where-Object FeatureName -in @('Microsoft-Hyper-V-All','HypervisorPlatform','VirtualMachinePlatform',
            'Microsoft-Windows-Subsystem-Linux','Containers-DisposableClientVM') |
        Select-Object FeatureName,State
}
Observe 'vm_state' {
    $installDirectory = (Get-ItemProperty 'HKLM:\SOFTWARE\Oracle\VirtualBox').InstallDir
    & (Join-Path $installDirectory 'VBoxManage.exe') list runningvms
    if ($LASTEXITCODE -ne 0) { throw 'VBoxManage readback failed.' }
}
Observe 'power_failure_log' {
    $source = Join-Path $env:USERPROFILE 'HCL VMs\topo1\device6\Logs\VBox.log'
    $copy = Join-Path $runDirectory 'device6-VBox.log'
    Copy-Item -LiteralPath $source -Destination $copy
    @{path=$copy; sha256=(Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash}
}
if ($receipt.errors.Count -eq 0) { $receipt.status = 'verified' }
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding UTF8
$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $destination 'latest.json') -Encoding UTF8
