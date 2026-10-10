<#
.SYNOPSIS
Preview a dedicated standard-user lab account; explicit actions create or retire it.
.DESCRIPTION
Preview is read-only except for a new receipt directory. Create prompts for a
SecureString password. Disable/Remove require the SID and marker from the
creation receipt and never delete a user profile, VM, media or original account.
#>
[CmdletBinding()]
param(
    [ValidateSet('Preview','Create','Disable','Remove')][string]$Action = 'Preview',
    [ValidatePattern('^[A-Za-z][A-Za-z0-9_-]{0,19}$')][string]$AccountName = 'MCPHCLLab',
    [string]$OutputRoot = (Join-Path $PSScriptRoot '..\work\lab-account-plans'),
    [string]$RecordFile,
    [ValidatePattern('^mcphcl-account-[0-9a-f]{32}$')][string]$PasswordPipe
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitProcess) { throw 'Use 64-bit Windows PowerShell.' }

function Current-Sid { [Security.Principal.WindowsIdentity]::GetCurrent().User.Value }
function Require-Administrator {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'This explicit account action requires an administrator PowerShell window.'
    }
}
function Save-Record($Record) {
    $receiptDirectory = Join-Path ([IO.Path]::GetFullPath($OutputRoot)) ([Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $receiptDirectory -ErrorAction Stop | Out-Null
    $receiptFile = Join-Path $receiptDirectory 'result.json'
    $Record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receiptFile -Encoding UTF8
    [pscustomobject]@{ record_file=$receiptFile; result=$Record } | ConvertTo-Json -Depth 9
}
function No-Lab-Processes {
    $names = @('SimwareClient.exe','SimwareWrapper.exe','SimwareMultiCC.exe','putty.exe','VBoxHeadless.exe','VirtualBoxVM.exe')
    $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.Name -in $names })
    if ($processes.Count) { throw 'HCL, console or guest processes still exist. Have their owner stop/sign out; no process will be killed.' }
}
function Load-Record {
    if (-not $RecordFile) { throw 'Supply the exact plan/creation RecordFile.' }
    $record = Get-Content -LiteralPath $RecordFile -Encoding UTF8 -Raw | ConvertFrom-Json
    if ($record.schema_version -ne 1 -or $record.owner_sid -ne (Current-Sid)) {
        throw 'Record schema or original owner SID does not match.'
    }
    if ($record.account_name -ne $AccountName) { throw 'AccountName must match the record.' }
    return $record
}
function Match-Lab-Account($Record) {
    if ($Record.kind -ne 'lab_account_creation' -or -not $Record.account_sid -or
        $Record.description -notmatch '^MCP_HCL lab [0-9a-f]{32}$') { throw 'Creation identity is missing.' }
    $account = Get-LocalUser -SID $Record.account_sid -ErrorAction Stop
    if ($account.Name -ne $AccountName -or $account.Description -ne $Record.description -or
        $account.SID.Value -eq $Record.owner_sid) { throw 'Account SID/name/marker mismatch; action refused.' }
    $profiles = @(Get-CimInstance Win32_UserProfile -ErrorAction Stop | Where-Object { $_.SID -eq $Record.account_sid })
    if (@($profiles | Where-Object { $_.Loaded -or $_.Special }).Count) { throw 'Lab profile must be signed out and must not be a system profile.' }
    return $account
}
function Receive-Lab-Password {
    if (-not $PasswordPipe) { return (Read-Host 'Password for the dedicated lab user' -AsSecureString) }
    # The same owner sends DPAPI-protected bytes through an owner-only pipe.
    # Neither the plaintext nor the protected credential is an argv/file value.
    Add-Type -AssemblyName System.Security
    $client = [IO.Pipes.NamedPipeClientStream]::new('.', $PasswordPipe, [IO.Pipes.PipeDirection]::In)
    $reader = $null
    $plain = $null
    $characters = $null
    $secure = $null
    try {
        $client.Connect(15000)
        $reader = [IO.StreamReader]::new($client, [Text.Encoding]::ASCII)
        $line = $reader.ReadLine()
        if (-not $line -or $line.Length -gt 16384) { throw 'Protected password channel returned no bounded value.' }
        $protected = [Convert]::FromBase64String($line)
        $plain = [Security.Cryptography.ProtectedData]::Unprotect($protected, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $characters = [Text.Encoding]::UTF8.GetChars($plain)
        $secure = [Security.SecureString]::new()
        foreach ($character in $characters) { $secure.AppendChar($character) }
        $secure.MakeReadOnly()
        return $secure
    } catch {
        if ($null -ne $secure) { $secure.Dispose() }
        throw
    } finally {
        if ($null -ne $plain) { [Array]::Clear($plain,0,$plain.Length) }
        if ($null -ne $characters) { [Array]::Clear($characters,0,$characters.Length) }
        if ($null -ne $reader) { $reader.Dispose() }
        $client.Dispose()
    }
}

switch ($Action) {
    'Preview' {
        $accounts = @(Get-LocalUser -ErrorAction Stop)
        $groups = @(Get-LocalGroup -ErrorAction Stop)
        $ownerProfile = [Environment]::GetFolderPath('UserProfile')
        $candidateProfile = Join-Path (Split-Path -Parent $ownerProfile) $AccountName
        $exists = [bool](@($accounts | Where-Object { $_.Name -eq $AccountName }).Count)
        $groupCollision = [bool](@($groups | Where-Object { $_.Name -eq $AccountName }).Count)
        $record = [ordered]@{
            schema_version=1; kind='lab_account_plan'; status='prepared'; action_executed='Preview'
            account_name=$AccountName; owner_sid=(Current-Sid); owner_profile=$ownerProfile
            account_exists=$exists; group_name_exists=$groupCollision
            predicted_profile=$candidateProfile; predicted_profile_exists=(Test-Path -LiteralPath $candidateProfile)
            proposed_group_sid='S-1-5-32-545'; proposed_group=(Get-LocalGroup -SID 'S-1-5-32-545').Name
            protected_runtime=(Join-Path $ownerProfile 'HCL VMs')
            protected_registry=(Join-Path $ownerProfile '.VirtualBox\VirtualBox.xml')
            shared_hcl_installation='D:\HCL'; changes_applied=$false
            runtime_isolation_verified=$false; full_live_gate_passed=$false
        }
        if ($exists -or $groupCollision -or $record.predicted_profile_exists) { $record.status='rejected' }
        Save-Record $record
    }
    'Create' {
        Require-Administrator
        $plan = Load-Record
        if ($plan.kind -ne 'lab_account_plan' -or $plan.status -ne 'prepared') { throw 'A prepared Preview plan is required.' }
        No-Lab-Processes
        $currentProfile = [Environment]::GetFolderPath('UserProfile')
        if ($currentProfile -ne $plan.owner_profile) { throw 'Original profile identity changed.' }
        if (@(Get-LocalUser | Where-Object { $_.Name -eq $AccountName }).Count -or
            @(Get-LocalGroup | Where-Object { $_.Name -eq $AccountName }).Count -or
            (Test-Path -LiteralPath $plan.predicted_profile)) { throw 'Account/profile name is no longer unused.' }
        $marker = 'MCP_HCL lab ' + [Guid]::NewGuid().ToString('N')
        $record = [ordered]@{schema_version=1;kind='lab_account_creation';status='partial';account_name=$AccountName
            owner_sid=$plan.owner_sid;owner_profile=$plan.owner_profile;account_sid=$null;description=$marker
            source_plan=([IO.Path]::GetFullPath($RecordFile));changes_applied=$false;runtime_isolation_verified=$false
            full_live_gate_passed=$false;profile_deleted=$false;error=$null}
        $labPassword = Receive-Lab-Password
        try {
            $account = New-LocalUser -Name $AccountName -Password $labPassword -Description $marker
            $record.account_sid = $account.SID.Value
            $record.changes_applied = $true
            $users = Get-LocalGroup -SID 'S-1-5-32-545'
            if (-not @(Get-LocalGroupMember -Group $users | Where-Object { $_.SID.Value -eq $account.SID.Value }).Count) {
                Add-LocalGroupMember -Group $users -Member $account
            }
            $admins = Get-LocalGroupMember -Group (Get-LocalGroup -SID 'S-1-5-32-544')
            if (@($admins | Where-Object { $_.SID.Value -eq $account.SID.Value }).Count) { throw 'New account unexpectedly has Administrators membership.' }
            $record.status = 'created_standard_account'
        } catch {
            $record.error = $_.Exception.Message
            # Capture a possible partially-created account; never guess that
            # an exception means no side effect and never repeat New-LocalUser.
            $observed = @(Get-LocalUser | Where-Object { $_.Name -eq $AccountName -and $_.Description -eq $marker })
            if ($observed.Count -eq 1) { $record.account_sid=$observed[0].SID.Value; $record.changes_applied=$true }
        } finally {
            if ($null -ne $labPassword) { $labPassword.Dispose() }
            Save-Record $record
        }
        if ($record.status -ne 'created_standard_account') { throw 'Creation was partial; inspect the saved receipt before any recovery.' }
    }
    'Disable' {
        Require-Administrator
        $record = Load-Record
        No-Lab-Processes
        $account = Match-Lab-Account $record
        Disable-LocalUser -SID $account.SID
        if ((Get-LocalUser -SID $account.SID).Enabled) { throw 'Disable readback failed.' }
        Save-Record ([ordered]@{schema_version=1;kind='lab_account_disabled';status='verified';account_name=$AccountName
            owner_sid=$record.owner_sid;account_sid=$account.SID.Value;changes_applied=$true;profile_deleted=$false})
    }
    'Remove' {
        Require-Administrator
        $record = Load-Record
        No-Lab-Processes
        $account = Match-Lab-Account $record
        if ($account.Enabled) { throw 'Disable the recorded lab account first; Remove will not act on an enabled account.' }
        Remove-LocalUser -SID $account.SID
        if (@(Get-LocalUser | Where-Object { $_.SID.Value -eq $record.account_sid }).Count) { throw 'Account removal readback failed.' }
        Save-Record ([ordered]@{schema_version=1;kind='lab_account_removed';status='verified';account_name=$AccountName
            owner_sid=$record.owner_sid;account_sid=$record.account_sid;changes_applied=$true;profile_deleted=$false})
    }
}
