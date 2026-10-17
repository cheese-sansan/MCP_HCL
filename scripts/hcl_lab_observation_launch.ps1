<# Execute only the reviewed read-only observer in a hidden lab-account process.
   Password input is a SecureString; never an argument, environment value or file. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CreationRecord,
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z]:[\\/]')][string]$ExpectedProfile,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ObserverSha256,
    [Parameter(Mandatory=$true)][string]$OutputRoot,
    [Security.SecureString]$Password,
    [switch]$PlanOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5) {
    throw 'This reviewed cross-account launcher requires Windows PowerShell 5.1. PowerShell 7 inherited the original account environment in a real observation; do not run it there or override user environment paths.'
}
foreach ($module in @('Microsoft.PowerShell.Security','Microsoft.PowerShell.Utility','Microsoft.PowerShell.Management','CimCmdlets')) {
    Import-Module (Join-Path $PSHOME ('Modules\'+$module+'\'+$module+'.psd1')) -ErrorAction Stop
}
function New-LabObservationCommand([string]$Reader,[string]$Sha256,[string]$Sid,[string]$Profile) {
    if ($Sha256 -notmatch '^[0-9a-fA-F]{64}$' -or $Sid -notmatch '^S-\d+(?:-\d+)+$' -or
        $Profile -notmatch '^[A-Za-z]:[\\/]' -or $Reader -notmatch '^[A-Za-z]:[\\/]' -or
        $Reader -match '[\x00-\x1f]' -or $Profile -match '[\x00-\x1f]') { throw 'Invalid observation command constants' }
    $literal={param($s) "'"+$s.Replace("'","''")+"'"}
    # All constants are escaped; bytes are hashed and executed from the same
    # buffer. Command mode does not change/bypass Windows execution policy.
    return '$b=[IO.File]::ReadAllBytes('+(& $literal $Reader)+');'+
        '$h=[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($b)).Replace(''-'','''');'+
        'if($h -ne '+(& $literal $Sha256)+'){throw ''Observer hash changed''};'+
        '&([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString($b).TrimStart([char]0xfeff))) '+
        '-ExpectedSid '+(& $literal $Sid)+' -ExpectedProfile '+(& $literal $Profile)
}
$reader=Join-Path $PSScriptRoot 'hcl_lab_environment_identity.ps1'
$expectedHash=$ObserverSha256.ToLowerInvariant()
if ((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'Reviewed observer content changed.' }
$creation=Get-Content -LiteralPath $CreationRecord -Encoding UTF8 -Raw|ConvertFrom-Json
$ownerSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if ($creation.schema_version -ne 1 -or $creation.kind -ne 'lab_account_creation' -or
    $creation.status -ne 'created_standard_account' -or $creation.owner_sid -ne $ownerSid -or
    $creation.account_sid -notmatch '^S-\d+(?:-\d+)+$' -or $creation.account_sid -eq $ownerSid -or
    $creation.account_name -notmatch '^[A-Za-z][A-Za-z0-9_-]{0,19}$' -or
    $creation.description -notmatch '^MCP_HCL lab [0-9a-f]{32}$') { throw 'A current-owner standard-account creation receipt is required.' }
$account=Get-LocalUser -SID $creation.account_sid
if (-not $account.Enabled -or $account.Name -ne $creation.account_name -or
    $account.SID.Value -ne $creation.account_sid -or $account.Description -ne $creation.description) { throw 'Lab account creation identity changed.' }
$admins=@(Get-LocalGroupMember -SID 'S-1-5-32-544')
if (@($admins|Where-Object {$_.SID.Value -eq $creation.account_sid}).Count) { throw 'Administrator membership refused.' }
$labProfile=@(Get-CimInstance Win32_UserProfile -Filter ("SID='"+$creation.account_sid+"'"))
if ($labProfile.Count -gt 1 -or ($labProfile.Count -eq 1 -and
    -not [string]::Equals([IO.Path]::GetFullPath($labProfile[0].LocalPath),[IO.Path]::GetFullPath($ExpectedProfile),[StringComparison]::OrdinalIgnoreCase))) { throw 'Registered profile identity differs.' }
# Cross-account logon has been observed to derive HOMEDRIVE/HOMEPATH from
# WorkingDirectory. Never fall back to SystemRoot or the receipt directory.
$profileReady=($labProfile.Count -eq 1 -and (Test-Path -LiteralPath $ExpectedProfile -PathType Container))
$actualWorkingDirectory=$ExpectedProfile
$operation=[Guid]::NewGuid().ToString('N')
$directory=Join-Path ([IO.Path]::GetFullPath($OutputRoot)) $operation
New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
$directory=(Resolve-Path -LiteralPath $directory).Path
$outputFile=Join-Path $directory 'stdout.json'
$errorFile=Join-Path $directory 'stderr.txt'
$record=[ordered]@{ operation_id=$operation; scope='authorized_hidden_actual_lab_readonly_observation'; account_sid=$account.SID.Value; observer_sha256=$expectedHash; credential_in_argv=$false; credential_in_files=$false; hidden_window=$true; hcl_or_guest_started=$false; profile_loaded_for_child=$false; profile_load_requested=$false; activation_allowed=$false;runtime_isolation_verified=$false;full_live_gate_passed=$false;phase='credential_input'; stdout_file=$outputFile; stderr_file=$errorFile }
$record['observation']='Environment'
$record['expected_profile']=$ExpectedProfile
$record['profile_ready']=$profileReady
$record['working_directory']=$actualWorkingDirectory
$recordFile=Join-Path $directory 'launch.json'
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
$stagedReader=Join-Path $directory 'observer.ps1'
Copy-Item -LiteralPath $reader -Destination $stagedReader
if ((Get-FileHash -LiteralPath $stagedReader).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'Observer copy bytes changed.' }
$runner=New-LabObservationCommand -Reader $stagedReader -Sha256 $expectedHash -Sid $creation.account_sid -Profile $ExpectedProfile
if ($runner.Length -gt 900) { throw 'Observation command exceeds the cross-account launch budget.' }
if ($PlanOnly) {
    $record['phase']='prepared_not_executed'
    $record['activation_allowed']=$false
    $record|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $recordFile -Encoding UTF8
    $record|ConvertTo-Json -Depth 5
    return
}
if (-not $profileReady) {
    $record['phase']='profile_initialization_required'
    $record|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $recordFile -Encoding UTF8
    throw 'Initialize the recorded account profile before observation; no credential or process was requested.'
}
$passwordInput=$null
$credential=$null
$child=$null
try {
    $shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    # Command mode is permitted by Restricted policy without changing it.
    # The command contains only the SHA-checked observer and identity constants.
    $passwordInput=if($null -ne $Password){$Password.Copy()}else{Read-Host 'Secure lab password input' -AsSecureString}
    $credential=New-Object Management.Automation.PSCredential(('.\'+$creation.account_name),$passwordInput)
    $record['execution_mode']='sha_checked_observer_command_mode'
    # CreateProcessWithLogonW has a shorter command limit. Keep the reviewed
    # content in its public file and hash the same bytes in the child too.
    $child=Start-Process -FilePath $shell -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-Command',$runner) -Credential $credential -LoadUserProfile -WindowStyle Hidden -WorkingDirectory $actualWorkingDirectory -RedirectStandardOutput $outputFile -RedirectStandardError $errorFile -PassThru
    $record['pid']=$child.Id;$record['phase']='running';$record['profile_load_requested']=$true
    $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
    if (-not $child.WaitForExit(45000)) {
        $record['phase']='running_after_observation_timeout'
    } else {
        $record['exit_code']=$child.ExitCode;$record['phase']='terminal_observed'
        if (Test-Path -LiteralPath $outputFile) { $record['stdout_sha256']=(Get-FileHash -LiteralPath $outputFile).Hash.ToLowerInvariant() }
    }
} catch { $record['phase']='failed';$record['error']=$_.Exception.Message }
finally {
    $credential=$null
    if ($passwordInput) { $passwordInput.Dispose() }
    $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
}
$record | ConvertTo-Json -Depth 5
if ($record['phase'] -eq 'terminal_observed') {
    Get-Content -LiteralPath $outputFile -Raw
    if ($record['exit_code'] -ne 0) { exit 2 }
}
elseif ($record['phase'] -eq 'running_after_observation_timeout') { exit 3 }
elseif ($record['phase'] -eq 'failed') { exit 2 }
