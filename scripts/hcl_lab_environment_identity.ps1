<# Read-only identity/path diagnostics. Never starts HCL, changes environment,
   creates accounts, or authorizes activation. Run in the intended account. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^S-\d+(?:-\d+)+$')][string]$ExpectedSid,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z]:[\\/]')][string]$ExpectedProfile
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'

function Normalize-LabPath($Value) {
    if ($Value -isnot [string] -or $Value -notmatch '^[A-Za-z]:[\\/]' -or
        $Value -match '[\x00-\x1f]' -or $Value.Length -gt 32768) { return $null }
    try { return [IO.Path]::GetFullPath($Value).TrimEnd('\','/') } catch { return $null }
}

function Test-LabEnvironmentObservation($Observation, [string]$ExpectedSid, [string]$ExpectedProfile) {
    $get = {
        param($Object, $Name)
        if ($null -eq $Object) { return $null }
        if ($Object -is [Collections.IDictionary]) { return $Object[$Name] }
        $property=$Object.PSObject.Properties[$Name]
        if ($null -ne $property) { return $property.Value }
        return $null
    }
    $profile=Normalize-LabPath $ExpectedProfile
    if (-not $profile -or $ExpectedSid -notmatch '^S-\d+(?:-\d+)+$') { throw 'Invalid expected identity' }
    $paths=& $get $Observation 'paths'
    $drive=& $get $paths 'HOMEDRIVE'
    $homePath=& $get $paths 'HOMEPATH'
    $homePair=$null
    if ($drive -is [string] -and $homePath -is [string]) { $homePair=$drive+$homePath }
    $rules=@(
        @{field='identity.sid';value=(& $get $Observation 'sid');expected=$ExpectedSid;mode='literal'},
        @{field='identity.standard_account';value=(& $get $Observation 'standard_account');expected=$true;mode='boolean'},
        @{field='profile.cim';value=(& $get $Observation 'cim_profile');expected=$profile;mode='path'},
        @{field='profile.known_folder';value=(& $get $Observation 'profile');expected=$profile;mode='path'},
        @{field='USERPROFILE';value=(& $get $paths 'USERPROFILE');expected=$profile;mode='path'},
        @{field='known_application_data';value=(& $get $Observation 'application_data');expected=($profile+'\AppData\Roaming');mode='path'},
        @{field='APPDATA';value=(& $get $paths 'APPDATA');expected=($profile+'\AppData\Roaming');mode='path'},
        @{field='known_local_application_data';value=(& $get $Observation 'local_application_data');expected=($profile+'\AppData\Local');mode='path'},
        @{field='LOCALAPPDATA';value=(& $get $paths 'LOCALAPPDATA');expected=($profile+'\AppData\Local');mode='path'},
        @{field='TEMP';value=(& $get $paths 'TEMP');expected=($profile+'\AppData\Local\Temp');mode='within'},
        @{field='TMP';value=(& $get $paths 'TMP');expected=($profile+'\AppData\Local\Temp');mode='within'},
        @{field='HOMEDRIVE+HOMEPATH';value=$homePair;expected=$profile;mode='path'},
        @{field='HOME';value=(& $get $paths 'HOME');expected=$profile;mode='optional_path'},
        @{field='VBOX_USER_HOME';value=(& $get $paths 'VBOX_USER_HOME');expected='';mode='empty'}
    )
    $checks=New-Object 'Collections.Generic.List[object]'
    foreach ($rule in $rules) {
        $value=$rule.value
        $state='unknown'
        if ($rule.mode -eq 'boolean') {
            if ($value -is [bool]) { if ($value) {$state='passed'} else {$state='failed'} }
        } elseif ($rule.mode -eq 'empty') {
            if ($null -eq $value -or $value -ceq '') {$state='passed'}
            elseif ($value -is [string]) {$state='failed'}
        } elseif ($rule.mode -eq 'literal') {
            if ($value -is [string] -and $value) {
                if ($value -ceq $rule.expected) {$state='passed'} else {$state='failed'}
            }
        } elseif ($rule.mode -eq 'optional_path' -and ($null -eq $value -or $value -ceq '')) {
            $state='passed'
        } else {
            $normalized=Normalize-LabPath $value
            if ($null -ne $normalized) {
                $matches=[string]::Equals($normalized,$rule.expected,[StringComparison]::OrdinalIgnoreCase)
                if ($rule.mode -eq 'within') {
                    $matches=$matches -or $normalized.StartsWith($rule.expected+'\',[StringComparison]::OrdinalIgnoreCase)
                }
                if ($matches) {$state='passed'} else {$state='failed'}
            }
        }
        $observed=$null
        # Export only named path/token scalars, never arbitrary objects or a
        # complete process environment, which can contain credentials.
        if ($value -is [string] -and $value.Length -le 32768 -and $value -notmatch '[\x00-\x1f]') {$observed=$value}
        elseif ($value -is [bool]) {$observed=$value}
        $checks.Add([pscustomobject]@{field=$rule.field;status=$state;expected=$rule.expected;observed=$observed})
    }
    $blockers=@($checks | Where-Object {$_.status -eq 'failed'} | ForEach-Object {$_.field})
    $unknown=@($checks | Where-Object {$_.status -eq 'unknown'} | ForEach-Object {$_.field})
    $status='verified'
    if ($unknown.Count) {$status='unknown'}
    if ($blockers.Count) {$status='rejected'}
    return [pscustomobject][ordered]@{
        schema_version=1;scope='current_principal_and_lexical_environment_paths_only'
        status=$status;checks=@($checks.ToArray());blockers=$blockers;unknown_fields=$unknown
        environment_paths_match=($status -eq 'verified');activation_allowed=$false
        runtime_isolation_verified=$false;full_live_gate_passed=$false
    }
}

# Missing CIM data remains unknown; never guess from USERPROFILE or account name.
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$cimProfile=$null
try {
    $profiles=@(Get-CimInstance Win32_UserProfile -Filter ("SID='"+$identity.User.Value+"'") -ErrorAction Stop)
    if ($profiles.Count -eq 1) {$cimProfile=[string]$profiles[0].LocalPath}
} catch { $cimProfile=$null }
$paths=[ordered]@{}
foreach ($name in @('USERPROFILE','HOME','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','TEMP','TMP','VBOX_USER_HOME')) {
    $paths[$name]=[Environment]::GetEnvironmentVariable($name,'Process')
}
$principal=New-Object Security.Principal.WindowsPrincipal($identity)
$observation=[pscustomobject]@{
    sid=$identity.User.Value;cim_profile=$cimProfile
    standard_account=(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -and
        -not (@($identity.Groups | ForEach-Object {$_.Value}) -contains 'S-1-5-32-544'))
    profile=[Environment]::GetFolderPath('UserProfile')
    application_data=[Environment]::GetFolderPath('ApplicationData')
    local_application_data=[Environment]::GetFolderPath('LocalApplicationData');paths=$paths
}
$result=Test-LabEnvironmentObservation -Observation $observation -ExpectedSid $ExpectedSid -ExpectedProfile $ExpectedProfile
$result | Add-Member -NotePropertyName operation_id -NotePropertyValue ([Guid]::NewGuid().ToString('N'))
$result | ConvertTo-Json -Depth 8
if ($result.status -ne 'verified') { exit 2 }
