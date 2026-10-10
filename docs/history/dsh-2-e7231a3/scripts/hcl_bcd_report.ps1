# Read-only BCD report. Requires elevation (bcdedit refuses to enumerate otherwise).
# Writes raw output to a JSON file so it can be used from a new-window sudo run.
param([Parameter(Mandatory = $true)][string]$OutputPath)

$bcd = Join-Path $env:SystemRoot 'System32\bcdedit.exe'
$report = [ordered]@{
    when = (Get-Date).ToString('s')
    elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    lab_entry_guid = '{10311110-89bd-11f0-ad29-c0bfbeee1ce7}'
    queries = [ordered]@{}
}
$queries = [ordered]@{
    bootmgr = @('/enum', '{bootmgr}')
    fwbootmgr = @('/enum', '{fwbootmgr}')
    current = @('/enum', '{current}')
    osloader = @('/enum', 'osloader', '/v')
    lab_entry = @('/enum', $report.lab_entry_guid)
}
foreach ($name in $queries.Keys) {
    $lines = @(& $bcd $queries[$name] 2>&1)
    $report.queries[$name] = [ordered]@{
        arguments = $queries[$name]
        exit_code = $LASTEXITCODE
        output = ($lines -join "`n")
    }
}
$all = @(& $bcd '/enum' 'all' 2>&1)
$report.all_exit_code = $LASTEXITCODE
$report.all_output = ($all -join "`n")

$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
Write-Output "elevated=$($report.elevated) bootmgr_exit=$($report.queries.bootmgr.exit_code) lab_entry_exit=$($report.queries.lab_entry.exit_code)"
