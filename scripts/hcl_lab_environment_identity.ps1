<# Observe only identity and selected non-secret environment paths. #>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
if ($identity.User.Value -ne 'S-1-5-21-246709277-55761766-931132026-1006') { throw 'Actual lab SID required.' }
$profile=[Environment]::GetFolderPath('UserProfile')
$paths=[ordered]@{}
foreach ($name in @('USERPROFILE','HOME','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','TEMP','TMP','VBOX_USER_HOME')) {
    $paths[$name]=[Environment]::GetEnvironmentVariable($name,'Process')
}
$blockers=New-Object 'Collections.Generic.List[string]'
if (-not [string]::Equals($paths['USERPROFILE'],$profile,[StringComparison]::OrdinalIgnoreCase)) { $blockers.Add('process_userprofile_differs_from_actual_lab_profile') }
foreach ($name in @('HOME','APPDATA','LOCALAPPDATA','TEMP','TMP','VBOX_USER_HOME')) {
    if ($paths[$name] -match '(?i)[\\/]Users[\\/]w8p1p(?:[\\/]|$)') { $blockers.Add('original_owner_path_in_'+$name.ToLowerInvariant()) }
}
[ordered]@{ scope='actual_lab_identity_and_environment_paths_only'; account=$identity.Name; sid=$identity.User.Value; profile=$profile; paths=$paths; powershell_version=$PSVersionTable.PSVersion.ToString(); effective_execution_policy=(Get-ExecutionPolicy).ToString(); blockers=@($blockers.ToArray()); runtime_isolation_verified=$false; activation_allowed=$false; full_live_gate_passed=$false } | ConvertTo-Json -Depth 5
