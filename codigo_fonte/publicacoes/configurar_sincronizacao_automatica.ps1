[CmdletBinding()]
param(
    [switch]$Desativar,
    [switch]$Status,
    [switch]$Executar,
    [switch]$NaoIniciar,
    [string]$PythonPath,
    [string]$GitPath
)

$ErrorActionPreference = 'Stop'
$nomeTarefa = 'EA019-GitHub-AutoSync'
$caminhoTarefa = '\'
$raiz = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$worker = Join-Path $PSScriptRoot 'sincronizar_automaticamente.py'
$esteScript = $MyInvocation.MyCommand.Path
$powershellPath = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$descricao = "Sincronizacao automatica do projeto EA019 com origin/main. Projeto: $raiz"

if (([int][bool]$Desativar + [int][bool]$Status + [int][bool]$Executar) -gt 1) {
    throw 'Use apenas uma opcao entre -Desativar, -Status e -Executar.'
}

function Resolve-Python {
    param([string]$Preferido)
    $candidatos = @()
    if ($Preferido) { $candidatos += $Preferido }
    else {
        $candidatos += Join-Path $raiz '.venv\Scripts\python.exe'
        $candidatos += @(Get-Command python.exe, python3.exe -All -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Source)
    }
    foreach ($candidato in ($candidatos | Select-Object -Unique)) {
        if (-not $candidato -or $candidato -match '\\WindowsApps\\' -or
            -not (Test-Path -LiteralPath $candidato -PathType Leaf)) { continue }
        try {
            & $candidato -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>$null
            if ($LASTEXITCODE -eq 0) { return (Resolve-Path -LiteralPath $candidato).Path }
        }
        catch { if ($Preferido) { throw } }
    }
    throw 'Python 3.10 ou superior nao encontrado. Instale-o ou informe -PythonPath.'
}

function Resolve-Git {
    param([string]$Preferido)
    if ($Preferido) {
        if (-not (Test-Path -LiteralPath $Preferido -PathType Leaf)) {
            throw 'O executavel informado em -GitPath nao existe.'
        }
        return (Resolve-Path -LiteralPath $Preferido).Path
    }
    $comando = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $comando) { throw 'Git nao encontrado. Instale o Git for Windows.' }
    return $comando.Source
}

function Get-SyncRuntime {
    param([string]$GitExecutavel)
    $gitDir = & $GitExecutavel -C $raiz rev-parse --path-format=absolute --git-common-dir
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel localizar o repositorio Git.' }
    return Join-Path $gitDir 'auto-sync'
}

function Test-SyncTaskRunning {
    param([string]$Runtime)
    $atual = Get-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa
    $info = Get-ScheduledTaskInfo -TaskName $nomeTarefa -TaskPath $caminhoTarefa
    # 0x41301 indica instancia em execucao mesmo se a tarefa foi desabilitada.
    if ($atual.State -eq 'Running' -or $info.LastTaskResult -eq 267009) { return $true }
    $arquivoMonitor = Join-Path $Runtime 'monitor.json'
    if (Test-Path -LiteralPath $arquivoMonitor) {
        $monitor = Get-Content -LiteralPath $arquivoMonitor -Raw | ConvertFrom-Json
        if ($monitor.running -and $monitor.pid -gt 0) {
            $processo = Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$monitor.pid)
            return $processo.Name -ieq 'pythonw.exe' -and
                $processo.CommandLine -like ('*"' + $worker + '" --watch*')
        }
    }
    return $false
}

if ($Executar) {
    # Compatibilidade com a tarefa antiga e com execucoes manuais de um ciclo.
    $pythonExecutavel = Resolve-Python -Preferido $PythonPath
    $gitExecutavel = Resolve-Git -Preferido $GitPath
    & $pythonExecutavel $worker --repo $raiz --branch main --remote origin --quiet-seconds 15 --git $gitExecutavel
    exit $LASTEXITCODE
}

$identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
$usuarioSid = $identidade.User.Value
$tarefa = Get-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa -ErrorAction SilentlyContinue
if ($tarefa) {
    $acoes = @($tarefa.Actions)
    $proprietarioCorreto = $false
    try {
        $proprietario = $tarefa.Principal.UserId
        if ($proprietario -notmatch '^S-1-') {
            $contaProprietaria = New-Object Security.Principal.NTAccount($proprietario)
            $proprietario = $contaProprietaria.Translate([Security.Principal.SecurityIdentifier]).Value
        }
        $proprietarioCorreto = $proprietario -eq $usuarioSid
    }
    catch { $proprietarioCorreto = $false }
    $acaoCorreta = $false
    if ($acoes.Count -eq 1) {
        $acaoAntiga = $acoes[0].Execute -eq $powershellPath -and
            $acoes[0].Arguments -match ('-File\s+"' + [regex]::Escape($esteScript) + '"\s+-Executar(?:\s|$)')
        $acaoMonitor = [IO.Path]::GetFileName($acoes[0].Execute) -ieq 'pythonw.exe' -and
            $acoes[0].Arguments -match ('^"' + [regex]::Escape($worker) + '"\s+--watch\s+--repo\s+"' +
                [regex]::Escape($raiz) + '"(?:\s|$)')
        $acaoCorreta = $acaoAntiga -or $acaoMonitor
    }
    if (-not $acaoCorreta -or -not $proprietarioCorreto -or $tarefa.Description -ne $descricao) {
        throw "Ja existe uma tarefa chamada $nomeTarefa que nao pertence a este projeto/usuario. Ela foi preservada."
    }
}

if ($Status) {
    if (-not $tarefa) {
        Write-Host 'Sincronizacao automatica ainda nao instalada.'
        exit 0
    }
    $tarefa | Select-Object TaskName, State
    Get-ScheduledTaskInfo -TaskName $nomeTarefa -TaskPath $caminhoTarefa |
        Select-Object LastRunTime, LastTaskResult, NextRunTime
    $runtime = Get-SyncRuntime -GitExecutavel (Resolve-Git -Preferido $GitPath)
    foreach ($nome in @('status.json', 'monitor.json')) {
        $arquivo = Join-Path $runtime $nome
        if (Test-Path -LiteralPath $arquivo) { Get-Content -LiteralPath $arquivo -Raw }
    }
    exit 0
}

if ($Desativar) {
    if ($tarefa) {
        Disable-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa | Out-Null
        if ($tarefa.Actions[0].Arguments -match '\s--watch(?:\s|$)') {
            $runtime = Get-SyncRuntime -GitExecutavel (Resolve-Git -Preferido $GitPath)
            New-Item -ItemType Directory -Path $runtime -Force | Out-Null
            [IO.File]::WriteAllText((Join-Path $runtime 'stop-monitor'), '')
        }
    }
    Write-Host 'Sincronizacao desativada. Um envio em andamento pode terminar antes do monitor encerrar.'
    exit 0
}

if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) { throw "Sincronizador nao encontrado: $worker" }
$pythonExecutavel = Resolve-Python -Preferido $PythonPath
$pythonSemJanela = Join-Path (Split-Path -Parent $pythonExecutavel) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonSemJanela -PathType Leaf)) {
    throw 'pythonw.exe nao encontrado junto do Python. Repare a instalacao do Python para executar sem janelas.'
}
$gitExecutavel = Resolve-Git -Preferido $GitPath
$identidadeGitConfigurada = $false
try {
    $null = & $gitExecutavel -C $raiz var GIT_AUTHOR_IDENT 2>$null
    $identidadeGitConfigurada = $LASTEXITCODE -eq 0
}
catch {}
if (-not $identidadeGitConfigurada) {
    throw 'Configure user.name e user.email neste repositorio antes de instalar a sincronizacao automatica.'
}

$runtime = Get-SyncRuntime -GitExecutavel $gitExecutavel
if ($tarefa) {
    Disable-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa | Out-Null
    if ($tarefa.Actions[0].Arguments -match '\s--watch(?:\s|$)') {
        $runtime = Get-SyncRuntime -GitExecutavel $gitExecutavel
        New-Item -ItemType Directory -Path $runtime -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $runtime 'stop-monitor'), '')
    }
    $limite = (Get-Date).AddMinutes(5)
    while (Test-SyncTaskRunning -Runtime $runtime) {
        if ((Get-Date) -gt $limite) { throw 'O envio anterior ainda esta terminando. Aguarde e execute a instalacao novamente.' }
        Start-Sleep -Milliseconds 500
    }
}
$sinalParada = Join-Path $runtime 'stop-monitor'
if (Test-Path -LiteralPath $sinalParada) { Remove-Item -LiteralPath $sinalParada }

# pythonw usa o subsistema grafico do Windows: nao cria console nem Terminal.
$argumentos = '"' + $worker + '" --watch --repo "' + $raiz +
    '" --branch main --remote origin --quiet-seconds 15 --git "' + $gitExecutavel + '"'
$acao = New-ScheduledTaskAction -Execute $pythonSemJanela -Argument $argumentos -WorkingDirectory $raiz
$login = New-ScheduledTaskTrigger -AtLogOn -User $usuarioSid
$principal = New-ScheduledTaskPrincipal -UserId $usuarioSid -LogonType Interactive -RunLevel Limited
$configuracao = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa -Action $acao `
    -Trigger @($login) -Principal $principal -Settings $configuracao -Description $descricao -Force | Out-Null
Enable-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa | Out-Null
if (-not $NaoIniciar) { Start-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa }
Write-Host "Sincronizacao instalada: $nomeTarefa (por alteracao, apos 15 segundos sem novos salvamentos)."
Write-Host "Monitor em segundo plano, sem janelas. Projeto: $raiz"
