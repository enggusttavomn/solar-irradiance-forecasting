param(
    [string]$DocxPath,
    [string]$AuditDir,
    [ValidateRange(5, 120)][int]$TimeoutSeconds = 30,
    [switch]$Worker,
    [string]$WorkingCopy,
    [string]$PidFile,
    [string]$ResultFile
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$workspaceRoot = [IO.Path]::GetFullPath('C:/Users/gusta/Downloads/1) EA019 - TCC')
$templatePath = [IO.Path]::GetFullPath('C:/Users/gusta/Downloads/Modelo Relatório Final - EA019.EA006.docx')
$runtimeRoot = 'C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies'
$runtimePython = Join-Path $runtimeRoot 'python/python.exe'
$runtimePowerShell = Join-Path $runtimeRoot 'native/powershell/pwsh.exe'
function Assert-TaskPath([string]$PathToCheck) {
    $resolved = [IO.Path]::GetFullPath($PathToCheck)
    if (-not $resolved.StartsWith($workspaceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The document and audit paths must remain inside the task workspace.'
    }
    if ($resolved.Equals($templatePath, [StringComparison]::OrdinalIgnoreCase)) { throw 'The retained template is read-only.' }
    return $resolved
}
if ($Worker) {
    $WorkingCopy = Assert-TaskPath $WorkingCopy
    $word = $null; $documents = $null; $document = $null
    $existingWordPids = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    try {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false; $word.DisplayAlerts = 0; $word.AutomationSecurity = 3
        $createdWordPids = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue |
            Where-Object { $_.Id -notin $existingWordPids } | Select-Object -ExpandProperty Id)
        @{ pid = $(if ($createdWordPids.Count -eq 1) { $createdWordPids[0] } else { 0 });
           newlyCreated = $createdWordPids.Count -eq 1 } | ConvertTo-Json -Compress |
            Set-Content -LiteralPath $PidFile -Encoding utf8
        $documents = $word.Documents
        $document = $documents.Open($WorkingCopy, $false, $false, $false)
        if ($document.ReadOnly) { throw 'The refreshed working copy opened read-only.' }
        $tocCount = $document.TablesOfContents.Count
        for ($pass = 0; $pass -lt 2; $pass++) {
            [void]$document.Fields.Update()
            for ($i = 1; $i -le $tocCount; $i++) { $document.TablesOfContents.Item($i).Update() }
            $document.Repaginate()
            foreach ($firstRange in $document.StoryRanges) {
                $range = $firstRange
                while ($null -ne $range) {
                    [void]$range.Fields.Update()
                    $next = $range.NextStoryRange
                    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($range)
                    $range = $next
                }
            }
        }
        for ($i = 1; $i -le $tocCount; $i++) { $document.TablesOfContents.Item($i).UpdatePageNumbers() }
        $document.Repaginate()
        $document.Save()
        @{ refreshed = $WorkingCopy; pages = $document.ComputeStatistics(2); tablesOfContents = $tocCount;
           fields = $document.Fields.Count } | ConvertTo-Json -Compress |
            Set-Content -LiteralPath $ResultFile -Encoding utf8
    }
    finally {
        if ($null -ne $document) {
            try { $document.Close(0) } catch {}
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
        }
        if ($null -ne $documents) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($documents) }
        if ($null -ne $word) {
            try { $word.Quit(0) } catch {}
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
        }
        [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    }
    exit
}
if ([string]::IsNullOrWhiteSpace($DocxPath)) { throw '-DocxPath is required.' }
$DocxPath = Assert-TaskPath $DocxPath
if ([IO.Path]::GetExtension($DocxPath) -ne '.docx') { throw 'Only editable DOCX copies are accepted.' }
if (-not (Test-Path -LiteralPath $DocxPath -PathType Leaf)) { throw 'The authored DOCX is missing.' }
if ((Get-FileHash -LiteralPath $DocxPath -Algorithm SHA256).Hash -eq 'AECEE899B62D0042F5104D90332A6FB0FD13A90779CB69FB3EA7DF4740E3E9D1') {
    throw 'A byte-identical copy of the retained template must not be modified.'
}
if ([string]::IsNullOrWhiteSpace($AuditDir)) {
    $AuditDir = Join-Path $PSScriptRoot ('field-refresh-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
}
$AuditDir = Assert-TaskPath $AuditDir
if (Test-Path -LiteralPath $AuditDir) { throw 'Use a new, unused audit directory for each refresh.' }
[void](New-Item -ItemType Directory -Path $AuditDir)
$authoredCopy = Join-Path $AuditDir 'authored-before-fields.docx'
$refreshedCopy = Join-Path $AuditDir 'word-refreshed.docx'
Copy-Item -LiteralPath $DocxPath -Destination $authoredCopy
Copy-Item -LiteralPath $DocxPath -Destination $refreshedCopy
$pidRecord = Join-Path $AuditDir 'word-process.json'
$resultRecord = Join-Path $AuditDir 'word-result.json'
$startInfo = [Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = $runtimePowerShell
$startInfo.UseShellExecute = $false; $startInfo.CreateNoWindow = $true
$startInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
$startInfo.RedirectStandardOutput = $true; $startInfo.RedirectStandardError = $true
foreach ($argument in @('-NoLogo', '-NoProfile', '-NonInteractive', '-File', $PSCommandPath, '-Worker',
                         '-WorkingCopy', $refreshedCopy, '-PidFile', $pidRecord, '-ResultFile', $resultRecord)) {
    $startInfo.ArgumentList.Add($argument)
}
$workerProcess = [Diagnostics.Process]::new(); $workerProcess.StartInfo = $startInfo
[void]$workerProcess.Start()
$stdoutTask = $workerProcess.StandardOutput.ReadToEndAsync()
$stderrTask = $workerProcess.StandardError.ReadToEndAsync()
if (-not $workerProcess.WaitForExit($TimeoutSeconds * 1000)) {
    $workerProcess.Kill($true)
    if (Test-Path -LiteralPath $pidRecord) {
        $owned = Get-Content -LiteralPath $pidRecord -Raw | ConvertFrom-Json
        if ($owned.newlyCreated -and $owned.pid) { Stop-Process -Id $owned.pid -ErrorAction SilentlyContinue }
    }
    throw "Word field refresh exceeded $TimeoutSeconds seconds. The authored DOCX remains unchanged."
}
$stdoutTask.Result | Set-Content -LiteralPath (Join-Path $AuditDir 'word-stdout.log') -Encoding utf8
$stderrTask.Result | Set-Content -LiteralPath (Join-Path $AuditDir 'word-stderr.log') -Encoding utf8
if ($workerProcess.ExitCode -ne 0) { throw "Word refresh failed; inspect $AuditDir. The authored DOCX remains unchanged." }
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
& $runtimePython (Join-Path $PSScriptRoot 'transplant_updated_document.py') --authored $authoredCopy `
    --refreshed $refreshedCopy --output $DocxPath --audit (Join-Path $AuditDir 'package-preservation-audit.json')
if ($LASTEXITCODE -ne 0) { throw "Relationship/package validation failed. The authored DOCX remains unchanged; inspect $AuditDir." }
Get-Content -LiteralPath $resultRecord -Raw
Write-Output ('Finalized editable DOCX: ' + $DocxPath)
