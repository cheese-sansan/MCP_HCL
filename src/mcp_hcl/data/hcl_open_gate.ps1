param(
    [Parameter(Mandatory = $true)][int]$HclPid,
    [Parameter(Mandatory = $true)][string]$ProjectFile,
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [switch]$ValidateOnly,
    [switch]$ResumeOpenDialog,
    [switch]$ResumeLoadedProject,
    [switch]$OpenOnly,
    [Parameter(Mandatory = $true)][string]$WorkspaceWorkRoot
)

$ErrorActionPreference = 'Stop'
if ($ResumeOpenDialog -and $ResumeLoadedProject) { throw 'Choose one explicit resume phase' }
if ($OpenOnly -and $ResumeLoadedProject) { throw 'OpenOnly cannot resume a save phase' }
$workRoot = [IO.Path]::GetFullPath($WorkspaceWorkRoot)
$projectFullPath = [IO.Path]::GetFullPath($ProjectFile)
$receiptRoot = [IO.Path]::GetFullPath($OutputDirectory)
foreach ($path in @($projectFullPath, $receiptRoot)) {
    if (-not $path.StartsWith($workRoot + [IO.Path]::DirectorySeparatorChar,
                              [StringComparison]::OrdinalIgnoreCase)) {
        throw "Gate files must be below $workRoot"
    }
    $ancestor = [IO.Path]::GetDirectoryName($path)
    while ($ancestor.StartsWith($workRoot, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $ancestor) {
            $item = Get-Item -LiteralPath $ancestor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Linked gate directories are not accepted'
            }
        }
        if ($ancestor -eq $workRoot) { break }
        $ancestor = [IO.Path]::GetDirectoryName($ancestor)
    }
}
if ([IO.Path]::GetExtension($projectFullPath) -ne '.net' -or
    -not (Test-Path -LiteralPath $projectFullPath -PathType Leaf)) {
    throw 'ProjectFile must identify an existing isolated .net project'
}
if ((Get-Item -LiteralPath $projectFullPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Linked project files are not accepted'
}
New-Item -ItemType Directory -Path $receiptRoot -Force | Out-Null
$latestReceiptPath = Join-Path $receiptRoot 'result.json'
# Archive receipts from older probe versions before introducing per-run output.
if (Test-Path -LiteralPath $latestReceiptPath) {
    $legacyReceipt = $null
    try { $legacyReceipt = [IO.File]::ReadAllText($latestReceiptPath, [Text.Encoding]::UTF8) | ConvertFrom-Json }
    catch { }
    if ($null -eq $legacyReceipt -or -not $legacyReceipt.operation_id) {
        $legacyDirectory = Join-Path $receiptRoot ('runs\prior_' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $legacyDirectory -Force | Out-Null
        Copy-Item -LiteralPath $latestReceiptPath -Destination (Join-Path $legacyDirectory 'result.json')
    }
}
$operationId = [Guid]::NewGuid().ToString('N')
$receiptDirectory = Join-Path $receiptRoot ('runs\' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + '_' + $operationId)
New-Item -ItemType Directory -Path $receiptDirectory -Force | Out-Null
$receiptPath = Join-Path $receiptDirectory 'result.json'
$report = [ordered]@{
    schema_version = 1
    status = 'rejected'
    hcl_pid = $HclPid
    project_file = $projectFullPath
    operation = $(if ($OpenOnly) { 'isolated_project_open' } elseif ($ResumeLoadedProject) { 'isolated_project_save' } else { 'isolated_project_open_save' })
    operation_id = $operationId
    receipt_directory = $receiptDirectory
    validate_only = [bool]$ValidateOnly
    open_only = [bool]$OpenOnly
    resume_open_dialog = [bool]$ResumeOpenDialog
    resume_loaded_project = [bool]$ResumeLoadedProject
    full_live_gate_passed = $false
    checks = [ordered]@{
        project_preconditions = $false
        accessibility = $false
        file_chooser_observed = $false
        project_opened = $false
        canvas_project_identity = $false
        save_invoked = $false
        project_readback = $false
        device_and_link_mutation = 'not_run'
        power_readback = 'not_run'
        console_readback = 'not_run'
    }
    evidence = @()
    started_at = [DateTime]::UtcNow.ToString('o')
}

try {
    function Read-Metadata([string]$path) {
        try {
            $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
            return ([IO.File]::ReadAllText($path, $strictUtf8) | ConvertFrom-Json)
        }
        catch { throw 'Project metadata is not valid UTF-8 JSON' }
    }
    $projectDirectory = [IO.Path]::GetDirectoryName($projectFullPath)
    $metadataPath = Join-Path $projectDirectory 'project.json'
    $originalProjectText = [IO.File]::ReadAllText($projectFullPath)
    $workingDirectories = [regex]::Matches($originalProjectText, '(?m)^    workingdir = ([^\r\n]*)')
    if ($workingDirectories.Count -ne 1 -or
        $workingDirectories[0].Groups[1].Value -ne $projectDirectory) {
        throw 'The isolated project must point its workingdir to its own directory before opening'
    }
    if ((Get-Item -LiteralPath $metadataPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'Linked project metadata is not accepted'
    }
    $projectMetadata = Read-Metadata $metadataPath
    if ([string]::IsNullOrWhiteSpace([string]$projectMetadata.projectInfo.name) -or
        $projectMetadata.deviceInfoList -isnot [System.Array]) {
        throw 'Project metadata needs a nonempty name and a deviceInfoList array'
    }
    foreach ($device in $projectMetadata.deviceInfoList) {
        $configPath = [IO.Path]::GetFullPath((Join-Path $projectDirectory $device.configPath))
        if (-not $configPath.StartsWith((Join-Path $projectDirectory 'DeviceConfig') + '\',
                                        [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Device configuration paths must remain inside the isolated DeviceConfig directory'
        }
        foreach ($itemPath in @($configPath, [IO.Path]::GetDirectoryName($configPath))) {
            if ((Get-Item -LiteralPath $itemPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Linked device configurations are not accepted'
            }
        }
    }
    $report.checks.project_preconditions = $true
    if ($ValidateOnly) {
        $report.status = 'verified'
        $report.verified_scope = 'isolated_project_preconditions_only'
        return
    }
    $process = Get-Process -Id $HclPid -ErrorAction Stop
    if ($process.ProcessName -ne 'SimwareClient') {
        throw 'HclPid does not identify an HCL workspace'
    }
    if ((Get-Process -Id $HclPid -ErrorAction Stop).ProcessName -ne 'SimwareClient') {
        throw 'HclPid must identify the HCL SimwareClient process'
    }
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    Add-Type -AssemblyName System.Drawing
    if (-not ('HclGateNative' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class HclGateNative {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int capacity);
    [DllImport("user32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint message, IntPtr wparam,
        StringBuilder text, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll", EntryPoint="SendMessageTimeoutW", CharSet=CharSet.Unicode, SetLastError=true)]
    public static extern IntPtr SetTextTimeout(IntPtr hwnd, uint message, IntPtr wparam,
        string text, uint flags, uint timeout, out IntPtr result);
    [DllImport("user32.dll", EntryPoint="SendMessageTimeoutW", ExactSpelling=true, SetLastError=true)]
    public static extern IntPtr ButtonTimeout(IntPtr hwnd, uint message, IntPtr wparam,
        IntPtr lparam, uint flags, uint timeout, out IntPtr result);
}
'@
    }
    function Find-Element($parent, [string]$property, [string]$value) {
        $propertyId = [System.Windows.Automation.AutomationElement]::${property}
        $condition = New-Object System.Windows.Automation.PropertyCondition($propertyId, $value)
        return $parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
    }
    function Invoke-Element($element) {
        if ($null -eq $element -or -not $element.Current.IsEnabled) {
            throw 'Requested HCL control is missing or disabled'
        }
        $pattern = $null
        if (-not $element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,
                                               [ref]$pattern)) {
            throw 'Requested HCL control has no InvokePattern'
        }
        ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
    }
    function Find-FileDialog {
        $desktop = [System.Windows.Automation.AutomationElement]::RootElement
        $pidCondition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $HclPid)
        $windows = $desktop.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCondition)
        $dialogCandidates = @()
        foreach ($window in $windows) {
            if ($window.Current.ClassName -eq '#32770') { $dialogCandidates += $window }
        }
        if ($dialogCandidates.Count -gt 1) { throw 'Multiple HCL native dialogs are present' }
        if ($dialogCandidates.Count -eq 1) { return $dialogCandidates[0] }
        return (Find-Element $hclWindow 'ClassNameProperty' '#32770')
    }
    function Save-HclImage([string]$name) {
        $rect = $hclWindow.Current.BoundingRectangle
        $bitmap = New-Object System.Drawing.Bitmap([int]$rect.Width, [int]$rect.Height)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $point = New-Object System.Drawing.Point([int]$rect.Left, [int]$rect.Top)
            $graphics.CopyFromScreen($point, [System.Drawing.Point]::Empty, $bitmap.Size)
            $bitmap.Save((Join-Path $receiptDirectory $name), [System.Drawing.Imaging.ImageFormat]::Png)
        }
        finally { $graphics.Dispose(); $bitmap.Dispose() }
    }
    function Invoke-NativeButton($element) {
        if ($element.Current.ClassName -ne 'Button' -or
            $element.Current.NativeWindowHandle -eq 0 -or -not $element.Current.IsEnabled) {
            throw 'Requested native file-dialog button is not available'
        }
        $buttonResult = [IntPtr]::Zero
        $buttonCall = [HclGateNative]::ButtonTimeout([IntPtr]$element.Current.NativeWindowHandle,
            0x00F5, [IntPtr]::Zero, [IntPtr]::Zero, 2, 10000, [ref]$buttonResult)
        if ($buttonCall -eq [IntPtr]::Zero) { throw 'Native button invocation timed out; its outcome is unknown' }
    }

    # MainWindowHandle can refer to the active file chooser. Select the actual
    # Workspace from current process-owned top-level UIA windows instead.
    $desktop = [System.Windows.Automation.AutomationElement]::RootElement
    $pidCondition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $HclPid)
    $processWindows = $desktop.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCondition)
    $workspaceCandidates = @()
    foreach ($window in $processWindows) {
        if ($window.Current.ClassName -eq 'Workspace') { $workspaceCandidates += $window }
    }
    if ($workspaceCandidates.Count -ne 1) {
        throw 'Exactly one accessible HCL Workspace is required at the same Windows integrity level'
    }
    $hclWindow = $workspaceCandidates[0]
    $report.hcl_main_handle = $hclWindow.Current.NativeWindowHandle
    if (-not $ResumeLoadedProject) {
    $browseId = 'MainWindow.Dialog_PopBaseWindow.widget_Main.widget_paint.Dialog.horizontalLayoutWidget.pushButton_browse_project'
    $fileDialog = Find-FileDialog
    if ($ResumeOpenDialog) {
        if ($null -eq $fileDialog) { throw 'There is no HCL file chooser to resume' }
        $report.checks.accessibility = $true
    }
    else {
        if ($null -ne $fileDialog) { throw 'An existing file dialog requires explicit -ResumeOpenDialog' }
        $homeDialog = Find-Element $hclWindow 'ClassNameProperty' 'HCLHomeView'
        if ($null -eq $homeDialog) {
            throw 'An accessible HCL Home dialog is required; run this probe at the same Windows integrity level as HCL'
        }
        $report.checks.accessibility = $true
        $browse = Find-Element $homeDialog 'AutomationIdProperty' $browseId
        [HclGateNative]::SetForegroundWindow([IntPtr]$homeDialog.Current.NativeWindowHandle) | Out-Null
        Save-HclImage 'before.png'
        Invoke-Element $browse
        $deadline = [DateTime]::UtcNow.AddSeconds(5)
        do {
            $fileDialog = Find-FileDialog
            if ($null -eq $fileDialog) { Start-Sleep -Milliseconds 100 }
        } while ($null -eq $fileDialog -and [DateTime]::UtcNow -lt $deadline)
    }
    if ($null -eq $fileDialog) { throw 'HCL did not open the file chooser' }
    $report.checks.file_chooser_observed = $true
    $controls = $fileDialog.FindAll([System.Windows.Automation.TreeScope]::Descendants,
                                    [System.Windows.Automation.Condition]::TrueCondition)
    $fileNameField = $null
    $openButton = $null
    foreach ($control in $controls) {
        if ($control.Current.ClassName -eq 'Edit' -and $control.Current.AutomationId -eq '1148') {
            $fileNameField = $control
        }
        if ($control.Current.ClassName -eq 'Button' -and $control.Current.AutomationId -eq '1') {
            $openButton = $control
        }
    }
    if ($null -eq $fileNameField -or $null -eq $openButton) { throw 'File chooser controls were not identified' }
    $dialogHandle = [IntPtr]$fileDialog.Current.NativeWindowHandle
    [HclGateNative]::SetForegroundWindow($dialogHandle) | Out-Null
    Start-Sleep -Milliseconds 200
    if ([HclGateNative]::GetForegroundWindow() -ne $dialogHandle) { throw 'HCL file chooser did not acquire focus' }
    if ($ResumeOpenDialog) { Save-HclImage 'before.png' }
    $editHandle = [IntPtr]$fileNameField.Current.NativeWindowHandle
    if ($editHandle -eq [IntPtr]::Zero) { throw 'File name field has no native handle' }
    $setResult = [IntPtr]::Zero
    $setCall = [HclGateNative]::SetTextTimeout($editHandle, 0x000C, [IntPtr]::Zero,
        $projectFullPath, 2, 2000, [ref]$setResult)
    if ($setCall -eq [IntPtr]::Zero -or $setResult -eq [IntPtr]::Zero) {
        throw 'Setting the isolated project path failed'
    }
    $buffer = New-Object System.Text.StringBuilder 2048
    $textResult = [IntPtr]::Zero
    $textCall = [HclGateNative]::SendMessageTimeout([IntPtr]$fileNameField.Current.NativeWindowHandle,
        0x000D, [IntPtr]$buffer.Capacity, $buffer, 2, 2000, [ref]$textResult)
    if ($textCall -eq [IntPtr]::Zero) { throw 'File name read-back timed out' }
    $report.path_field_readback = $buffer.ToString()
    $report.path_input_method = 'WM_SETTEXT/WM_GETTEXT'
    Save-HclImage 'after-path-entry.png'
    if ($buffer.ToString() -ne $projectFullPath) { throw 'The selected path failed read-back before opening' }
    if ([HclGateNative]::GetForegroundWindow() -ne $dialogHandle) { throw 'Focus changed before opening the isolated project' }
    Invoke-NativeButton $openButton
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        $fileDialog = Find-FileDialog
        if ($null -ne $fileDialog) { Start-Sleep -Milliseconds 100 }
    } while ($null -ne $fileDialog -and [DateTime]::UtcNow -lt $deadline)
    if ($null -ne $fileDialog) { throw 'HCL did not close the file chooser after opening; no success is claimed' }
    $remainingHome = Find-Element $hclWindow 'ClassNameProperty' 'HCLHomeView'
    if ($null -ne $remainingHome -and -not $remainingHome.Current.IsOffscreen) {
        throw 'HCL remained on its Home screen after opening'
    }
    $report.checks.project_opened = $true
    $report.evidence += [ordered]@{ layer = 'gui'; action = 'open'; selector = $browseId }
    }
    else {
        if ($null -ne (Find-FileDialog)) { throw 'Close or explicitly resume the current native dialog before saving' }
        $report.checks.accessibility = $true
        Save-HclImage 'before.png'
        $report.evidence += [ordered]@{ layer = 'gui'; action = 'observe_previously_opened_project' }
    }
    # HCL exposes the project identity in the Workspace's own caption, not
    # necessarily among its descendant controls. Require both name and path.
    $captionBuffer = New-Object System.Text.StringBuilder 4096
    [HclGateNative]::GetWindowText([IntPtr]$hclWindow.Current.NativeWindowHandle,
        $captionBuffer, $captionBuffer.Capacity) | Out-Null
    $caption = $captionBuffer.ToString()
    $report.active_project_caption = $caption
    $captionMatch = [regex]::Match($caption, '^HCL - (?<name>.+) \[(?<path>.+)\]$')
    if ($captionMatch.Success -and
        $captionMatch.Groups['name'].Value.Equals([string]$projectMetadata.projectInfo.name, [StringComparison]::Ordinal) -and
        [IO.Path]::GetFullPath($captionMatch.Groups['path'].Value).Equals($projectDirectory, [StringComparison]::OrdinalIgnoreCase)) {
        $report.checks.project_opened = $true
        $report.checks.canvas_project_identity = $true
        $report.evidence += [ordered]@{ layer = 'gui'; project_caption = $caption }
    }
    if (-not $report.checks.canvas_project_identity) {
        Save-HclImage 'after-open-unverified.png'
        throw 'The active isolated project identity could not be verified before saving'
    }
    if ($OpenOnly) {
        $report.status = 'verified'
        $report.verified_scope = 'gui_project_identity_only'
        return
    }
    $saveId = 'MainWindow.centralWidget.frameTitleBar.frameTopToolBar.frameTitleTool.toolButtonSave'
    Invoke-Element (Find-Element $hclWindow 'AutomationIdProperty' $saveId)
    $report.checks.save_invoked = $true
    Start-Sleep -Seconds 1
    $metadata = Read-Metadata $metadataPath
    $net = [IO.File]::ReadAllText($projectFullPath)
    $expectedDirectory = [IO.Path]::GetDirectoryName($projectFullPath)
    $savedWorkingDirectory = [regex]::Match($net, '(?m)^    workingdir = ([^\r\n]*)').Groups[1].Value
    if (-not $savedWorkingDirectory.Equals($expectedDirectory, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The saved project working directory changed unexpectedly'
    }
    $report.checks.project_readback = $true
    $report.evidence += [ordered]@{
        layer = 'project_file'
        sha256 = (Get-FileHash -LiteralPath $projectFullPath -Algorithm SHA256).Hash
        project_name = $metadata.projectInfo.name
        device_count = $metadata.deviceInfoList.Count
    }
    Save-HclImage 'after-save.png'
    $report.status = 'partial'
}
catch {
    if ($report.checks.project_opened) { $report.status = 'partial' }
    $report.error = $_.Exception.Message
    $report.error_type = $_.Exception.GetType().FullName
    if ($null -ne $hclWindow) {
        try { Save-HclImage 'failure.png' } catch { }
    }
}
finally {
    $report.completed_at = [DateTime]::UtcNow.ToString('o')
    $json = $report | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($receiptPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText($latestReceiptPath, $json, (New-Object System.Text.UTF8Encoding($false)))
    $json
}
