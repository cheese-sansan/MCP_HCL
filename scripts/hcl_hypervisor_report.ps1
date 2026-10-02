# Read-only hypervisor / optional-feature report. Requires elevation.
# Purpose: decide whether VirtualBox can be made to work WITHOUT changing boot
# configuration (i.e. whether the Windows Hypervisor Platform API is present).
param([Parameter(Mandatory = $true)][string]$OutputPath)

$report = [ordered]@{
    when = (Get-Date).ToString('s')
    elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    features = [ordered]@{}
    device_guard = $null
    bcd_current = $null
    vboxmanage_version = $null
    error = $null
}

try {
    # WHPX is the API VirtualBox's NEM backend needs to run alongside Hyper-V.
    $wanted = @('HypervisorPlatform', 'Microsoft-Hyper-V-All', 'Microsoft-Hyper-V',
                'Microsoft-Hyper-V-Hypervisor', 'VirtualMachinePlatform',
                'Containers-DisposableClientVM')
    foreach ($name in $wanted) {
        try {
            $f = Get-WindowsOptionalFeature -Online -FeatureName $name -ErrorAction Stop
            $report.features[$name] = $f.State
        } catch {
            $report.features[$name] = "unavailable: $($_.Exception.Message)"
        }
    }

    try {
        $dg = Get-CimInstance -ClassName Win32_DeviceGuard -Namespace 'root\Microsoft\Windows\DeviceGuard' -ErrorAction Stop
        $report.device_guard = [ordered]@{
            virtualization_based_security_status = $dg.VirtualizationBasedSecurityStatus
            security_services_running = ($dg.SecurityServicesRunning -join ',')
            security_services_configured = ($dg.SecurityServicesConfigured -join ',')
            available_security_properties = ($dg.AvailableSecurityProperties -join ',')
        }
    } catch {
        $report.device_guard = "unavailable: $($_.Exception.Message)"
    }

    $bcd = Join-Path $env:SystemRoot 'System32\bcdedit.exe'
    $report.bcd_current = ((& $bcd '/enum' '{current}' 2>&1) -join "`n")

    $vbox = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
    if (Test-Path -LiteralPath $vbox) {
        $report.vboxmanage_version = ((& $vbox --version 2>&1) -join "`n").Trim()
    }
} catch {
    $report.error = $_.Exception.Message
} finally {
    New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($OutputPath)) -Force | Out-Null
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
    Write-Output "written: $OutputPath"
}
