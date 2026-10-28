[CmdletBinding()]
param(
    [ValidateRange(3, 300)]
    [int]$AtrasoSegundos = 12
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$artigo = Join-Path $raiz 'artigos\revista_unificado'
$sincronizadorGithub = Join-Path $PSScriptRoot 'sincronizar_github_artigo.ps1'
$pastaLog = Join-Path $env:LOCALAPPDATA 'TCC\OverleafSync'
$arquivoLog = Join-Path $pastaLog 'monitor.log'
$mutex = New-Object Threading.Mutex($false, 'Local\TCCOverleafMonitor')
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'Never'

if (-not $mutex.WaitOne(0)) {
    exit 0
}

New-Item -ItemType Directory -Path $pastaLog -Force | Out-Null

function Write-Log {
    param([string]$Mensagem)
    $linha = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' - ' + $Mensagem
    Add-Content -LiteralPath $arquivoLog -Value $linha -Encoding UTF8
}

function Invoke-ScriptSincronizacao {
    param(
        [string]$Nome,
        [string]$Script
    )
    Write-Log ('Iniciando sincronizacao com ' + $Nome + '.')
    $preferenciaAnterior = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $saida = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Script 2>&1 | Out-String)
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = $preferenciaAnterior
    if ($saida) {
        Add-Content -LiteralPath $arquivoLog -Value $saida.TrimEnd() -Encoding UTF8
    }
    if ($codigo -eq 0) {
        Write-Log ('Sincronizacao com ' + $Nome + ' concluida.')
    }
    else {
        Write-Log ('Sincronizacao com ' + $Nome + ' falhou com codigo ' + $codigo + '.')
    }
}

function Invoke-Sincronizacao {
    Write-Log 'Alteracao detectada; publicando a fonte oficial no GitHub.'
    Invoke-ScriptSincronizacao -Nome 'GitHub' -Script $sincronizadorGithub
}

$monitor = New-Object IO.FileSystemWatcher $artigo, '*'
$monitor.IncludeSubdirectories = $true
$monitor.NotifyFilter = [IO.NotifyFilters]'FileName, DirectoryName, LastWrite, Size'

try {
    Write-Log 'Monitor automatico iniciado.'
    Invoke-Sincronizacao

    while ($true) {
        $alteracao = $monitor.WaitForChanged([IO.WatcherChangeTypes]::All)
        if ($alteracao.TimedOut) { continue }

        do {
            $alteracao = $monitor.WaitForChanged(
                [IO.WatcherChangeTypes]::All,
                $AtrasoSegundos * 1000
            )
        } while (-not $alteracao.TimedOut)

        Invoke-Sincronizacao
    }
}
finally {
    $monitor.Dispose()
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
