<# Execute only the reviewed read-only observer in a hidden lab-account process.
   Password input is a SecureString; never an argument, environment value or file. #>
[CmdletBinding()]
param([ValidateSet('Profile','Environment')][string]$Observation='Profile')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5) {
    throw 'This reviewed cross-account launcher requires Windows PowerShell 5.1. PowerShell 7 inherited the original account environment in a real observation; do not run it there or override user environment paths.'
}
$reader='C:\Users\Public\Documents\MCP_HCL_Lab_ReadOnly_20261006\hcl_lab_profile_observation.ps1'
$expectedHash='7256d14fa55ea27f7e2edf283d55a71e78f2bee97190d20ea363eb4d0cb217eb'
if ($Observation -eq 'Environment') {
    $reader='C:\Users\Public\Documents\MCP_HCL_Lab_ReadOnly_20261006\hcl_lab_environment_identity.ps1'
    $expectedHash='24baca3a7c4e16d4a4a7bacb0de1b9628f41f71348cdfc43619adb9f2cffa3f4'
}
if ((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) { throw 'Reviewed observer content changed.' }
$account=Get-LocalUser -Name MCPHCLLab
if ($account.SID.Value -ne 'S-1-5-21-246709277-55761766-931132026-1006' -or -not $account.Enabled -or $account.Description -ne 'MCP_HCL lab c051c9911b5744c194924c0b39121aa0') { throw 'Lab account creation identity changed.' }
$labProfile=@(Get-CimInstance Win32_UserProfile -Filter "SID='S-1-5-21-246709277-55761766-931132026-1006'")
if ($labProfile.Count -ne 1 -or [string]::IsNullOrEmpty($labProfile[0].LocalPath)) { throw 'One registered lab profile is required.' }
$actualWorkingDirectory=$labProfile[0].LocalPath
$operation=[Guid]::NewGuid().ToString('N')
$directory=Join-Path $PSScriptRoot ('..\work\lab-profile-readonly-20261006\'+$operation)
New-Item -ItemType Directory -Path $directory -ErrorAction Stop | Out-Null
$directory=(Resolve-Path -LiteralPath $directory).Path
$outputFile=Join-Path $directory 'stdout.json'
$errorFile=Join-Path $directory 'stderr.txt'
$record=[ordered]@{ operation_id=$operation; scope='authorized_hidden_actual_lab_readonly_observation'; account_sid=$account.SID.Value; observer_sha256=$expectedHash; credential_in_argv=$false; credential_in_files=$false; hidden_window=$true; hcl_or_guest_started=$false; profile_loaded_for_child=$true; phase='credential_input'; stdout_file=$outputFile; stderr_file=$errorFile }
$record['observation']=$Observation
$record['working_directory']=$actualWorkingDirectory
$recordFile=Join-Path $directory 'launch.json'
$record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
$passwordInput=Read-Host 'Secure lab password input' -AsSecureString
$credential=New-Object Management.Automation.PSCredential('.\MCPHCLLab',$passwordInput)
$child=$null
try {
    $shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    # Command mode is permitted by Restricted policy without changing it.
    # The encoded argument is only the SHA-checked observer, never a password.
    $runner='$p='''+$reader+''';$b=[IO.File]::ReadAllBytes($p);$h=[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($b)).Replace(''-'','''');if($h -ne '''+$expectedHash+'''){throw ''Observer hash changed''};&([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString($b)))'
    $record['execution_mode']='sha_checked_observer_command_mode'
    # CreateProcessWithLogonW has a shorter command limit. Keep the reviewed
    # content in its public file and hash the same bytes in the child too.
    $child=Start-Process -FilePath $shell -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-Command',$runner) -Credential $credential -LoadUserProfile -WindowStyle Hidden -WorkingDirectory $actualWorkingDirectory -RedirectStandardOutput $outputFile -RedirectStandardError $errorFile -PassThru
    $record['pid']=$child.Id;$record['phase']='running'
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
if ($record['phase'] -eq 'terminal_observed') { Get-Content -LiteralPath $outputFile -Raw }
elseif ($record['phase'] -eq 'failed') { exit 2 }
