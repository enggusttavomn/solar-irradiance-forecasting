param([switch]$SemAbrir)
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$urlPainel = 'http://127.0.0.1:8767'
function Testar-Painel {
    try {
        $saudePainel = Invoke-RestMethod -Uri ($urlPainel + '/health') -TimeoutSec 3
        if ($saudePainel.app -eq 'tcc-progresso-quantizacao-v1') { return $true }
        throw 'A porta 8767 esta ocupada por outro servico.'
    } catch [System.Net.WebException] {
        return $false
    }
}
if (-not (Testar-Painel)) {
    $candidatosPythonPainel = @(
        (Join-Path $raizProjeto '.venv/Scripts/python.exe'),
        (Join-Path $raizProjeto '.venv-baselines-gpu-20260912/Scripts/python.exe')
    )
    $pythonPainel = $candidatosPythonPainel | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $pythonPainel) { throw 'Python do projeto nao encontrado. Crie o ambiente .venv conforme o README.' }
    $pastaLogsPainel = Join-Path $raizProjeto 'relatorios/quantizacao_todos_modelos_20260929/painel'
    New-Item -ItemType Directory -Path $pastaLogsPainel -Force | Out-Null
    $stampPainel = Get-Date -Format 'yyyyMMdd_HHmmss'
    $processoPainel = Start-Process -FilePath $pythonPainel -ArgumentList @('-X','utf8','-m','codigo_fonte.acompanhamento.painel_progresso_quantizacao','--port','8767') -WorkingDirectory $raizProjeto -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $pastaLogsPainel ($stampPainel + '.log')) -RedirectStandardError (Join-Path $pastaLogsPainel ($stampPainel + '.erro.log'))
    $prontoPainel = $false
    for ($tentativaPainel = 0; $tentativaPainel -lt 20; $tentativaPainel++) {
        Start-Sleep -Milliseconds 500
        if (Testar-Painel) { $prontoPainel = $true; break }
        if ($processoPainel.HasExited) { throw ('O painel encerrou. Confira os logs em ' + $pastaLogsPainel) }
    }
    if (-not $prontoPainel) { throw ('O painel nao respondeu. Confira os logs em ' + $pastaLogsPainel) }
}
if (-not $SemAbrir) { Start-Process $urlPainel }
Write-Output ('Painel disponivel em ' + $urlPainel)
Write-Output 'Este monitor nao inicia nem encerra treinamentos.'
