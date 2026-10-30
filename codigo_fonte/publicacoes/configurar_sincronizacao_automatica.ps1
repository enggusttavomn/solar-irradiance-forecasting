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
    if ($Preferido) {
        $candidatos += $Preferido
    }
    else {
        $candidatos += Join-Path $raiz '.venv\Scripts\python.exe'
        $candidatos += @(Get-Command python.exe, python3.exe -All -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Source)
    }
    foreach ($candidato in ($candidatos | Select-Object -Unique)) {
        if (-not $candidato -or $candidato -match '\\WindowsApps\\' -or
            -not (Test-Path -LiteralPath $candidato -PathType Leaf)) {
            continue
        }
        try {
            & $candidato -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>$null
            if ($LASTEXITCODE -eq 0) {
                return (Resolve-Path -LiteralPath $candidato).Path
            }
        }
        catch {
            if ($Preferido) { throw }
        }
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

if ($Executar) {
    $pythonExecutavel = Resolve-Python -Preferido $PythonPath
    $gitExecutavel = Resolve-Git -Preferido $GitPath
    & $pythonExecutavel $worker --repo $raiz --branch main --remote origin --quiet-seconds 15 --git $gitExecutavel
    exit $LASTEXITCODE
}

$identidade = [Security.Principal.WindowsIdentity]::GetCurrent()
$usuarioSid = $identidade.User.Value
$usuarioNome = $identidade.Name
$tarefa = Get-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa -ErrorAction SilentlyContinue
if ($tarefa) {
    $acoes = @($tarefa.Actions)
    $proprietarioCorreto = $tarefa.Principal.UserId -in @($usuarioSid, $usuarioNome)
    $scriptEscapado = [regex]::Escape($esteScript)
    $acaoCorreta = $acoes.Count -eq 1 -and
        $acoes[0].Execute -eq $powershellPath -and
        $acoes[0].Arguments -match ('-File\s+"' + $scriptEscapado + '"\s+-Executar(?:\s|$)')
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
    $gitExecutavel = Resolve-Git -Preferido $GitPath
    $gitDir = & $gitExecutavel -C $raiz rev-parse --path-format=absolute --git-common-dir
    if ($LASTEXITCODE -eq 0) {
        $arquivoStatus = Join-Path $gitDir 'auto-sync\status.json'
        if (Test-Path -LiteralPath $arquivoStatus) {
            Get-Content -LiteralPath $arquivoStatus -Raw
        }
    }
    exit 0
}

if ($Desativar) {
    if ($tarefa) {
        Disable-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa | Out-Null
    }
    Write-Host 'Sincronizacao automatica desativada.'
    exit 0
}

if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
    throw "Sincronizador nao encontrado: $worker"
}
$pythonExecutavel = Resolve-Python -Preferido $PythonPath
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
$argumentos = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
    $esteScript + '" -Executar -PythonPath "' + $pythonExecutavel + '" -GitPath "' + $gitExecutavel + '"'
$acao = New-ScheduledTaskAction -Execute $powershellPath -Argument $argumentos -WorkingDirectory $raiz
$periodico = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$login = New-ScheduledTaskTrigger -AtLogOn -User $usuarioSid
$principal = New-ScheduledTaskPrincipal -UserId $usuarioSid -LogonType Interactive -RunLevel Limited
$configuracao = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa -Action $acao `
    -Trigger @($periodico, $login) -Principal $principal -Settings $configuracao `
    -Description $descricao -Force | Out-Null
if (-not $NaoIniciar) {
    Start-ScheduledTask -TaskName $nomeTarefa -TaskPath $caminhoTarefa
}
Write-Host "Sincronizacao automatica instalada: $nomeTarefa (a cada minuto e no login)."
Write-Host "Projeto: $raiz"
