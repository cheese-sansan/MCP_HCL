param([Parameter(Mandatory = $true)][int]$HclPid, [int]$BackendPort = 16600)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
if ($HclPid -lt 1) { throw 'HclPid must be positive' }
if ($BackendPort -lt 1024 -or $BackendPort -gt 65535) { throw 'BackendPort is invalid' }
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$profileRows = @(Get-CimInstance Win32_UserProfile -Filter "SID='$currentSid'")
if ($profileRows.Count -ne 1) { throw 'No unique current-SID Windows profile' }
# Check inherited paths before Add-Type can use the process Temp directory.
$identityProfilePath = [IO.Path]::GetFullPath([string]$profileRows[0].LocalPath)
foreach ($identityProfileObserved in @([Environment]::GetFolderPath('UserProfile'), $env:USERPROFILE)) {
    if (-not ([IO.Path]::GetFullPath([string]$identityProfileObserved).Equals($identityProfilePath, [StringComparison]::OrdinalIgnoreCase))) {
        throw 'Inherited profile paths disagree with the current SID'
    }
}
$identityTempRoot = [IO.Path]::GetFullPath((Join-Path $identityProfilePath 'AppData\Local\Temp'))
$identityTempPath = [IO.Path]::GetFullPath([string]$env:TEMP)
if (-not ($identityTempPath.Equals($identityTempRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $identityTempPath.StartsWith($identityTempRoot + '\', [StringComparison]::OrdinalIgnoreCase))) {
    throw 'Inherited Temp path disagrees with the current SID'
}
if (-not ('HclProcessIdentityNative' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class HclProcessIdentityNative {
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("advapi32.dll", SetLastError=true)]
    static extern bool OpenProcessToken(IntPtr process, uint access, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError=true)]
    static extern bool GetTokenInformation(IntPtr token, int kind, out int elevation,
        int size, out int returned);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    public static bool Elevated(int pid) {
        IntPtr process = OpenProcess(0x1000, false, pid);
        if (process == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        IntPtr token = IntPtr.Zero;
        try {
            if (!OpenProcessToken(process, 0x0008, out token))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            int elevated, returned;
            if (!GetTokenInformation(token, 20, out elevated, 4, out returned) || returned != 4)
                throw new Win32Exception(Marshal.GetLastWin32Error());
            return elevated != 0;
        } finally {
            if (token != IntPtr.Zero) CloseHandle(token);
            CloseHandle(process);
        }
    }
}
'@
}
$target = Get-CimInstance Win32_Process -Filter "ProcessId=$HclPid"
if ($null -eq $target) { throw 'HCL process missing' }
$owner = Invoke-CimMethod -InputObject $target -MethodName GetOwnerSid
$callerProcess = Get-Process -Id $PID
$targetProcess = Get-Process -Id $HclPid
$callerElevated = [HclProcessIdentityNative]::Elevated($PID)
$hclElevated = [HclProcessIdentityNative]::Elevated($HclPid)
$again = Get-CimInstance Win32_Process -Filter "ProcessId=$HclPid"
if ($null -eq $again -or $again.CreationDate -ne $target.CreationDate -or
    $again.ExecutablePath -ne $target.ExecutablePath -or $again.SessionId -ne $target.SessionId) {
    throw 'HCL process changed during observation'
}
$ownerAgain = Invoke-CimMethod -InputObject $again -MethodName GetOwnerSid
if ($ownerAgain.ReturnValue -ne $owner.ReturnValue -or $ownerAgain.Sid -ne $owner.Sid) {
    throw 'HCL process owner changed during observation'
}
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction Stop |
    Where-Object { $_.LocalAddress -in @('127.0.0.1', '0.0.0.0', '::1', '::') })
$listenerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($listenerPids.Count -ne 1) { throw 'No unique local backend listener process' }
$broker = Get-CimInstance Win32_Process -Filter "ProcessId=$($listenerPids[0])"
if ($null -eq $broker) { throw 'Backend listener process missing' }
$brokerOwner = Invoke-CimMethod -InputObject $broker -MethodName GetOwnerSid
$brokerElevated = [HclProcessIdentityNative]::Elevated([int]$broker.ProcessId)
$brokerAgain = Get-CimInstance Win32_Process -Filter "ProcessId=$($listenerPids[0])"
if ($null -eq $brokerAgain -or $brokerAgain.CreationDate -ne $broker.CreationDate -or
    $brokerAgain.ExecutablePath -ne $broker.ExecutablePath) { throw 'Backend process changed during observation' }
[ordered]@{
    schema_version = 1
    actual_sid = $currentSid
    cim_profile_directory = [string]$profileRows[0].LocalPath
    profile_directory = [Environment]::GetFolderPath('UserProfile')
    environment_profile = $env:USERPROFILE
    application_data = [Environment]::GetFolderPath('ApplicationData')
    environment_application_data = $env:APPDATA
    local_application_data = [Environment]::GetFolderPath('LocalApplicationData')
    environment_local_application_data = $env:LOCALAPPDATA
    temporary_directory = $env:TEMP
    caller = [ordered]@{ pid = $PID; session_id = $callerProcess.SessionId; elevated = $callerElevated }
    hcl = [ordered]@{
        pid = $HclPid
        name = [string]$target.Name
        owner_sid = [string]$owner.Sid
        owner_result = [int]$owner.ReturnValue
        session_id = [int]$target.SessionId
        creation_time = $target.CreationDate.ToUniversalTime().ToString('o')
        executable_path = [string]$target.ExecutablePath
        elevated = $hclElevated
        main_window_title = [string]$targetProcess.MainWindowTitle
    }
    broker = [ordered]@{
        pid = [int]$broker.ProcessId
        name = [string]$broker.Name
        owner_sid = [string]$brokerOwner.Sid
        owner_result = [int]$brokerOwner.ReturnValue
        session_id = [int]$broker.SessionId
        creation_time = $broker.CreationDate.ToUniversalTime().ToString('o')
        executable_path = [string]$broker.ExecutablePath
        elevated = $brokerElevated
        port = $BackendPort
        gui_connection_verified = $false
    }
} | ConvertTo-Json -Depth 5 -Compress
