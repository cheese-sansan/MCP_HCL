param(
    [Parameter(Mandatory = $true)][int]$HclPid,
    [Parameter(Mandatory = $true)][string]$ProjectFile,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [switch]$ValidateOnly,
    [switch]$ResumeOpenDialog,
    [switch]$ResumeLoadedProject,
    [switch]$OpenOnly
)
# Source checkout entry point; the packaged implementation is shared with MCP.
$implementation = Join-Path $PSScriptRoot '..\src\mcp_hcl\data\hcl_open_gate.ps1'
$workRoot = Join-Path $PSScriptRoot '..\work'
& $implementation @PSBoundParameters -WorkspaceWorkRoot $workRoot
