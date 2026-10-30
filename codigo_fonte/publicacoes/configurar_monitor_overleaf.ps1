[CmdletBinding()]
param([switch]$Remover)

$ErrorActionPreference = 'Stop'
$nomeValor = 'TCCOverleafSync'
$chaveRun = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

if ($Remover) {
    Remove-ItemProperty -Path $chaveRun -Name $nomeValor -ErrorAction SilentlyContinue
    Write-Host 'Monitor automatico removido.' -ForegroundColor Yellow
    exit 0
}

$monitor = Join-Path $PSScriptRoot 'monitorar_overleaf.ps1'
$argumentos = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $monitor + '"'
$comando = 'powershell.exe ' + $argumentos

New-Item -Path $chaveRun -Force | Out-Null
Set-ItemProperty -Path $chaveRun -Name $nomeValor -Value $comando
Start-Process -FilePath 'powershell.exe' -ArgumentList $argumentos -WindowStyle Hidden
Write-Host 'Monitor automatico configurado e iniciado.' -ForegroundColor Green
