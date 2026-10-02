param(
    [Parameter(Mandatory=$true)][ValidateSet('Create','Remove','Arm','Disarm')][string]$Action,
    [Parameter(Mandatory=$true)][string]$ReceiptDirectory,
    [string]$EntryId
)
# Run explicitly after approval. No automatic reboot or default boot change.
# Arm/Disarm use the firmware boot manager's one-shot 'bootsequence': the next
# boot goes straight into the lab entry and the setting clears itself, so the
# default entry is never modified and no menu timing is involved.
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'An elevated PowerShell is required.'
}
$workRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\work'))
$directory = [IO.Path]::GetFullPath($ReceiptDirectory)
if (-not $directory.StartsWith($workRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Receipt directory must be below repository work.'
}
$cursor = $directory
while ($cursor.Length -ge $workRoot.Length) {
    if ((Test-Path -LiteralPath $cursor) -and
        ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Receipt paths cannot contain reparse points.'
    }
    $cursor = Split-Path -Parent $cursor
}
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$runId = [Guid]::NewGuid().ToString('N')
$runDirectory = Join-Path $directory $runId
New-Item -ItemType Directory -Path $runDirectory | Out-Null
$receipt = [ordered]@{
    operation_id=$runId; timestamp_utc=[DateTime]::UtcNow.ToString('o')
    action=$Action; status='unverified'; entry_id=$null; commands=@()
    reboot_performed=$false; full_live_gate_passed=$false
}
$bcd = Join-Path $env:SystemRoot 'System32\bcdedit.exe'
function Run-Bcd([string[]]$BcdArguments) {
    $lines = @(& $bcd @BcdArguments 2>&1)
    $exitCode = $LASTEXITCODE
    $output = $lines -join "`n"
    $receipt.commands += @{arguments=$BcdArguments; exit_code=$exitCode; output=$output}
    if ($exitCode -ne 0) { throw "BCDEdit failed: $output" }
    return $output
}
function Try-Bcd([string[]]$BcdArguments) {
    # Probing helper: records the command but reports failure instead of throwing.
    $lines = @(& $bcd @BcdArguments 2>&1)
    $exitCode = $LASTEXITCODE
    $output = $lines -join "`n"
    $receipt.commands += @{arguments=$BcdArguments; exit_code=$exitCode; output=$output}
    return @{exit_code=$exitCode; output=$output}
}
function Get-OneShotTarget {
    # UEFI systems expose {fwbootmgr}; the Windows Boot Manager honours
    # bootsequence as well. Prefer the firmware boot manager.
    foreach ($candidate in '{fwbootmgr}','{bootmgr}') {
        $probe = Try-Bcd @('/enum',$candidate)
        if ($probe.exit_code -eq 0) { return $candidate }
    }
    return $null
}
$createdId = $null
try {
    if ($Action -eq 'Create') {
        if ($EntryId) { throw 'Create does not accept an existing entry ID.' }
        $existing = Run-Bcd -BcdArguments @('/enum','osloader')
        if ($existing -match 'MCP_HCL Lab') { throw 'A lab boot entry already exists; inspect it before continuing.' }
        $backup = Join-Path $runDirectory 'bcd-before.bak'
        Run-Bcd -BcdArguments @('/export',$backup) | Out-Null
        $receipt.backup = @{path=$backup; sha256=(Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash}
        $receipt.current_before = Run-Bcd -BcdArguments @('/enum','{current}')
        $receipt.boot_manager_before = Run-Bcd -BcdArguments @('/enum','{bootmgr}')
        $copyOutput = Run-Bcd -BcdArguments @('/copy','{current}','/d','MCP_HCL Lab (Hypervisor and VSM off)')
        $ids = @([regex]::Matches($copyOutput, '\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}'))
        if ($ids.Count -ne 1) { throw 'Cannot uniquely identify the new BCD entry; inspect the command receipt.' }
        $createdId = $ids[0].Value
        $receipt.entry_id = $createdId
        Run-Bcd -BcdArguments @('/set',$createdId,'hypervisorlaunchtype','off') | Out-Null
        Run-Bcd -BcdArguments @('/set',$createdId,'vsmlaunchtype','off') | Out-Null
        Run-Bcd -BcdArguments @('/displayorder',$createdId,'/addlast') | Out-Null
        $receipt.entry_readback = Run-Bcd -BcdArguments @('/enum',$createdId)
        $receipt.current_after = Run-Bcd -BcdArguments @('/enum','{current}')
        $receipt.boot_manager_after = Run-Bcd -BcdArguments @('/enum','{bootmgr}')
        if ($receipt.entry_readback -notmatch '(?im)^hypervisorlaunchtype\s+Off\s*$' -or
            $receipt.entry_readback -notmatch '(?im)^vsmlaunchtype\s+Off\s*$') {
            throw 'The new entry did not read back both disabled launch settings.'
        }
        if ($receipt.current_before -ne $receipt.current_after) { throw 'Current boot entry changed unexpectedly.' }
        $defaultBefore = [regex]::Match($receipt.boot_manager_before, '(?im)^default\s+(.+)$').Groups[1].Value.Trim()
        $defaultAfter = [regex]::Match($receipt.boot_manager_after, '(?im)^default\s+(.+)$').Groups[1].Value.Trim()
        if (-not $defaultBefore -or $defaultBefore -ne $defaultAfter) { throw 'Default boot entry changed unexpectedly.' }
        $receipt.status = 'verified'
        $receipt.verified_scope = 'lab_boot_entry_created_and_read_back_only'
        $receipt.next_step = 'Manually restart and select MCP_HCL Lab, then inspect HypervisorPresent and start one isolated HCL device.'
    } elseif ($Action -in @('Arm','Disarm')) {
        if ($EntryId -notmatch '^\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}$') {
            throw 'Arm/Disarm requires the exact lab GUID from a Create receipt.'
        }
        $receipt.entry_id = $EntryId
        $managerBefore = Run-Bcd -BcdArguments @('/enum','{bootmgr}')
        $defaultBefore = [regex]::Match($managerBefore, '(?im)^default\s+(.+)$').Groups[1].Value.Trim()
        if ($Action -eq 'Arm') {
            $entry = Run-Bcd -BcdArguments @('/enum',$EntryId)
            if ($entry -notmatch 'MCP_HCL Lab \(Hypervisor and VSM off\)') {
                throw 'The GUID is not an MCP_HCL lab entry.'
            }
            # Not every boot manager accepts bootsequence: on this machine
            # {fwbootmgr} enumerates but rejects the set with "element not found".
            # Try both and keep the one that actually reads back.
            $receipt.attempts = @()
            $armed = $null
            foreach ($candidate in '{bootmgr}','{fwbootmgr}') {
                $probe = Try-Bcd @('/enum',$candidate)
                if ($probe.exit_code -ne 0) {
                    $receipt.attempts += @{target=$candidate; result='not_enumerable'}
                    continue
                }
                $set = Try-Bcd @('/set',$candidate,'bootsequence',$EntryId)
                if ($set.exit_code -ne 0) {
                    $receipt.attempts += @{target=$candidate; result="set_failed: $($set.output)"}
                    continue
                }
                $readback = Try-Bcd @('/enum',$candidate)
                if ($readback.output -match [regex]::Escape($EntryId)) {
                    $armed = $candidate
                    $receipt.one_shot_readback = $readback.output
                    $receipt.attempts += @{target=$candidate; result='armed'}
                    break
                }
                $receipt.attempts += @{target=$candidate; result='readback_missing'}
            }
            if (-not $armed) {
                throw 'No boot manager accepted a one-shot bootsequence; select the entry from the boot menu instead.'
            }
            $receipt.one_shot_target = $armed
            $receipt.status = 'verified'
            $receipt.verified_scope = 'one_shot_boot_sequence_armed_and_read_back_only'
            $receipt.next_step = ('Use Restart (not Shutdown) once. The firmware will boot the lab entry ' +
                                  'automatically and clear bootsequence by itself.')
        } else {
            foreach ($candidate in '{bootmgr}','{fwbootmgr}') {
                $null = Try-Bcd @('/deletevalue',$candidate,'bootsequence')
            }
            $residual = @()
            foreach ($candidate in '{bootmgr}','{fwbootmgr}') {
                $probe = Try-Bcd @('/enum',$candidate)
                if ($probe.exit_code -eq 0 -and $probe.output -match '(?im)^bootsequence') {
                    $residual += $candidate
                }
            }
            if ($residual.Count -gt 0) {
                throw "bootsequence is still present on: $($residual -join ', ')"
            }
            $receipt.one_shot_target = 'cleared'
            $receipt.one_shot_readback = 'no bootsequence value remains'
            $receipt.status = 'verified'
            $receipt.verified_scope = 'one_shot_boot_sequence_cleared_and_read_back_only'
            $receipt.next_step = 'No pending one-shot boot; the next start uses the normal default entry.'
        }
        $managerAfter = Run-Bcd -BcdArguments @('/enum','{bootmgr}')
        $defaultAfter = [regex]::Match($managerAfter, '(?im)^default\s+(.+)$').Groups[1].Value.Trim()
        if (-not $defaultBefore -or $defaultBefore -ne $defaultAfter) {
            throw 'Default boot entry changed unexpectedly.'
        }
        $receipt.default_entry_unchanged = $defaultAfter
    } else {
        if ($EntryId -notmatch '^\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}$') {
            throw 'Remove requires the exact created GUID from a receipt.'
        }
        $entry = Run-Bcd -BcdArguments @('/enum',$EntryId)
        if ($entry -notmatch 'MCP_HCL Lab \(Hypervisor and VSM off\)') { throw 'The GUID is not an MCP_HCL lab entry.' }
        $current = Run-Bcd -BcdArguments @('/enum','{current}','/v')
        $bootManager = Run-Bcd -BcdArguments @('/enum','{bootmgr}','/v')
        if ($current -match [regex]::Escape($EntryId)) { throw 'Boot the normal Windows entry before removing the lab entry.' }
        if ($bootManager -match ('(?im)^default\s+' + [regex]::Escape($EntryId))) {
            throw 'The lab entry is currently the default; restore the normal default first.'
        }
        Run-Bcd -BcdArguments @('/delete',$EntryId) | Out-Null
        $remaining = Run-Bcd -BcdArguments @('/enum','osloader','/v')
        if ($remaining -match [regex]::Escape($EntryId)) { throw 'Deleted GUID is still present.' }
        $receipt.entry_id = $EntryId
        $receipt.status = 'verified'
        $receipt.verified_scope = 'lab_boot_entry_removed_and_read_back_only'
    }
} catch {
    $receipt.status = 'partial'
    $receipt.error = $_.Exception.Message
    if ($createdId) {
        try {
            Run-Bcd -BcdArguments @('/delete',$createdId) | Out-Null
            $receipt.rollback = 'new_entry_deleted'
        } catch { $receipt.rollback = "failed: $($_.Exception.Message)" }
    }
} finally {
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $runDirectory 'result.json') -Encoding UTF8
}
if ($receipt.status -ne 'verified') { throw $receipt.error }
