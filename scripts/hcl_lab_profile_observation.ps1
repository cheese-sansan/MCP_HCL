<# Read-only HCL/VirtualBox metadata from the actual MCPHCLLab session.
   Writes only a new receipt in that account's Documents directory.
   Does not invoke VBoxManage, start HCL, register VMs or alter settings. #>
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$actualProfile=[Environment]::GetFolderPath('UserProfile')
$expectedSid='S-1-5-21-246709277-55761766-931132026-1006'
if ($identity.User.Value -ne $expectedSid -or $identity.Name.Split('\')[-1] -ne 'MCPHCLLab') {
    throw 'Run this script in the existing MCPHCLLab account; identity did not match its creation SID.'
}
$operation=[Guid]::NewGuid().ToString('N')
$runtimeRoot=Join-Path $actualProfile 'HCL VMs'
$registryFile=Join-Path $actualProfile '.VirtualBox\VirtualBox.xml'
$blockers=New-Object 'Collections.Generic.List[string]'
$errors=New-Object 'Collections.Generic.List[string]'
$files=New-Object 'Collections.Generic.List[object]'
$machines=New-Object 'Collections.Generic.List[object]'
$groupSids=@($identity.Groups | ForEach-Object { $_.Value })
if ($groupSids -contains 'S-1-5-32-544') { $blockers.Add('administrator_group_present') }
if (-not [string]::IsNullOrEmpty($env:VBOX_USER_HOME)) { $blockers.Add('custom_vbox_user_home_needs_review') }
$processes=@(Get-Process -Name HCL,SimwareWrapper,VBoxHeadless,VirtualBoxVM,SimwareMultiCC -ErrorAction SilentlyContinue | Select-Object Name,Id,SessionId)
if ($processes.Count) { $blockers.Add('hcl_guest_or_console_process_present') }
$clock=[Diagnostics.Stopwatch]::StartNew()
$registryHash=$null
try {
    # Enumerating first distinguishes denied namespaces from nonexistent files.
    [IO.Directory]::EnumerateFileSystemEntries($actualProfile).GetEnumerator().MoveNext() | Out-Null
    if (Test-Path -LiteralPath $runtimeRoot) {
        $rootItem=Get-Item -LiteralPath $runtimeRoot -Force
        if ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked runtime root' }
        $queue=New-Object 'Collections.Generic.Queue[IO.DirectoryInfo]';$queue.Enqueue($rootItem)
        $visited=0
        while ($queue.Count) {
            foreach ($item in $queue.Dequeue().EnumerateFileSystemInfos()) {
                $visited++
                if ($visited -gt 4096 -or $clock.Elapsed.TotalSeconds -gt 5) { throw 'Inventory budget exceeded' }
                if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked runtime entry' }
                if ($item -is [IO.DirectoryInfo]) { $queue.Enqueue($item);continue }
                $descriptorHash=$null
                if ($item.Extension -in '.vbox','.vbox-prev') {
                    if ($item.Length -gt 1048576) { throw 'VM descriptor too large' }
                    $descriptorHash=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
                }
                $files.Add([pscustomobject]@{ path=$item.FullName.Substring($runtimeRoot.Length+1); size=$item.Length; mtime_utc=$item.LastWriteTimeUtc.ToString('o'); descriptor_sha256=$descriptorHash })
            }
        }
    }
    $registryDirectory=Split-Path -Parent $registryFile
    if (Test-Path -LiteralPath $registryDirectory) {
        [IO.Directory]::EnumerateFileSystemEntries($registryDirectory).GetEnumerator().MoveNext() | Out-Null
        $registryItem=Get-Item -LiteralPath $registryDirectory -Force
        if ($registryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked registry directory' }
    }
    if (Test-Path -LiteralPath $registryFile) {
        $registryItem=Get-Item -LiteralPath $registryFile -Force
        if ($registryItem.Length -gt 1048576 -or ($registryItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe registry file' }
        $registryHash=(Get-FileHash -LiteralPath $registryFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $settings=New-Object Xml.XmlReaderSettings;$settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit;$settings.XmlResolver=$null
        $reader=[Xml.XmlReader]::Create($registryFile,$settings)
        try { $xml=New-Object Xml.XmlDocument;$xml.XmlResolver=$null;$xml.Load($reader) } finally { $reader.Dispose() }
        foreach ($entry in $xml.SelectNodes("//*[local-name()='MachineEntry']")) {
            $uuid=$entry.GetAttribute('uuid');$source=$entry.GetAttribute('src')
            if ([string]::IsNullOrEmpty($uuid) -or [string]::IsNullOrEmpty($source)) { throw 'Incomplete machine registration' }
            $machines.Add([pscustomobject]@{ uuid=$uuid; configuration=$source })
            if ($source -match '(?i)[\\/]Users[\\/]w8p1p[\\/]') { $blockers.Add('original_owner_registration_reference') }
        }
    }
} catch { $errors.Add($_.Exception.Message) }
$receiptDirectory=Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('MCP_HCL_Receipts\profile-'+$operation)
$resolvedReceipt=[IO.Path]::GetFullPath($receiptDirectory)
if (-not $resolvedReceipt.StartsWith($actualProfile.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Receipt must remain in the actual lab profile' }
New-Item -ItemType Directory -Path $resolvedReceipt -ErrorAction Stop | Out-Null
$record=[ordered]@{ schema_version=1; operation_id=$operation; scope='actual_lab_identity_and_runtime_metadata_only'; account=$identity.Name; sid=$identity.User.Value; profile=$actualProfile; administrators_group_present=($groupSids -contains 'S-1-5-32-544'); runtime_root=$runtimeRoot; registry_file=$registryFile; vbox_user_home=$env:VBOX_USER_HOME; registry_sha256=$registryHash; runtime_files=@($files.ToArray()); registered_machines=@($machines.ToArray()); processes=$processes; errors=@($errors.ToArray()); blockers=@($blockers.ToArray()); runtime_isolation_verified=$false; activation_allowed=$false; full_live_gate_passed=$false }
$recordFile=Join-Path $resolvedReceipt 'profile-observation.json'
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $recordFile -Encoding UTF8
[ordered]@{ status=$(if ($errors.Count) {'unknown'} else {'observed'}); account=$identity.Name; sid=$identity.User.Value; profile=$actualProfile; runtime_file_count=$(if ($errors.Count) {$null} else {$files.Count}); registered_machine_count=$(if ($errors.Count) {$null} else {$machines.Count}); processes=$processes; errors=@($errors.ToArray()); blockers=@($blockers.ToArray()); receipt_file=$recordFile; runtime_isolation_verified=$false } | ConvertTo-Json -Depth 5
