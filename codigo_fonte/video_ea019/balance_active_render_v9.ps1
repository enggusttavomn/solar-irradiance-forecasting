$ErrorActionPreference = 'Stop'
$renderRoot = 'C:\Users\gusta\Downloads\1) EA019 - TCC'
$renderOutput = Join-Path $renderRoot 'documentacao\relatorio_final_ea019\video\completo_v9'
$methodProcess = @(Get-CimInstance Win32_Process -Filter "Name = 'blender.exe'" | Where-Object {
    $_.CommandLine -like "*$renderRoot*director_v9.py*--chapter metodologia --render*"
})
if ($methodProcess.Count -ne 1) { throw 'Expected exactly one owned methodology render.' }
Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class V9OwnedRenderScheduling {
 [DllImport("kernel32.dll", SetLastError=true)] public static extern IntPtr OpenProcess(uint access, bool inherit, uint id);
 [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr process);
 [DllImport("ntdll.dll")] public static extern int NtSuspendProcess(IntPtr process);
 [DllImport("ntdll.dll")] public static extern int NtResumeProcess(IntPtr process);
}
'@
$ownedRenderPid = [uint32]$methodProcess[0].ProcessId
$ownedHandle = [V9OwnedRenderScheduling]::OpenProcess(0x0800, $false, $ownedRenderPid)
if ($ownedHandle -eq [IntPtr]::Zero) { throw 'Cannot open the owned methodology render.' }
$temporarilyPaused = $false
$recordPath = Join-Path $renderOutput 'balanceamento_processos_v9.json'
try {
    $result = [V9OwnedRenderScheduling]::NtSuspendProcess($ownedHandle)
    if ($result -ne 0) { throw "Suspend failed: $result" }
    $temporarilyPaused = $true
    @{ status='temporarily_paused'; chapter='metodologia'; process_id=$ownedRenderPid; reason='Three-worker trial did not improve throughput; retain work in memory while two existing jobs finish.'; time=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding utf8
    Write-Output "V9_OWNED_RENDER_PAUSED $ownedRenderPid"
    $pauseStart = Get-Date
    while (((Get-Date) - $pauseStart).TotalMinutes -lt 45) {
        Start-Sleep -Seconds 5
        try { $renderQueue = Get-Content -LiteralPath (Join-Path $renderOutput 'fila_render_v9.json') -Raw | ConvertFrom-Json } catch { continue }
        if ($renderQueue.complete -contains 'entradas_tarefas' -or $renderQueue.complete -contains 'geografia') { break }
        if (($renderQueue.failed.PSObject.Properties | Measure-Object).Count -gt 0) { break }
        if (((Get-Date) - (Get-Item -LiteralPath (Join-Path $renderOutput 'fila_render_v9.json')).LastWriteTime).TotalSeconds -gt 30) { break }
    }
} finally {
    if ($temporarilyPaused) {
        $resumeResult = [V9OwnedRenderScheduling]::NtResumeProcess($ownedHandle)
        @{ status='resumed'; chapter='metodologia'; process_id=$ownedRenderPid; resume_status=$resumeResult; time=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding utf8
        Write-Output "V9_OWNED_RENDER_RESUMED $ownedRenderPid STATUS $resumeResult"
    }
    [void][V9OwnedRenderScheduling]::CloseHandle($ownedHandle)
}
