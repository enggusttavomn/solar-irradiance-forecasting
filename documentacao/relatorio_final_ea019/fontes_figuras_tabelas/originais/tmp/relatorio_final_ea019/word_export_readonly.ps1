param(
    [Parameter(Mandatory = $true)][string]$InputDocx,
    [Parameter(Mandatory = $true)][string]$OutputPdf,
    [Parameter(Mandatory = $true)][string]$PidFile
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$word = $null
$documents = $null
$document = $null
$existingWordPids = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ReadOnlyWordProcess {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
}
'@
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $wordProcessId = [uint32]0
    if ($null -ne $word.Hwnd) {
        [void][ReadOnlyWordProcess]::GetWindowThreadProcessId([IntPtr]$word.Hwnd, [ref]$wordProcessId)
    }
    else {
        $createdWordPids = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue |
            Where-Object { $_.Id -notin $existingWordPids } | Select-Object -ExpandProperty Id)
        if ($createdWordPids.Count -eq 1) { $wordProcessId = [uint32]$createdWordPids[0] }
    }
    @{ pid = $wordProcessId; newlyCreated = $wordProcessId -notin $existingWordPids } |
        ConvertTo-Json -Compress | Set-Content -LiteralPath $PidFile -Encoding utf8
    $documents = $word.Documents
    $document = $documents.Open($InputDocx, $false, $true, $false)
    $pageCount = $document.ComputeStatistics(2)
    $document.ExportAsFixedFormat($OutputPdf, 17)
    @{ converter = 'Microsoft Word COM'; readOnly = $document.ReadOnly; pages = $pageCount; pdf = $OutputPdf } |
        ConvertTo-Json -Compress | Write-Output
}
finally {
    if ($null -ne $document) {
        try { $document.Close(0) } catch {}
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($document)
    }
    if ($null -ne $documents) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($documents)
    }
    if ($null -ne $word) {
        try { $word.Quit(0) } catch {}
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
