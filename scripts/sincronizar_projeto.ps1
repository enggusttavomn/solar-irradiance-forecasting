[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot

function Invoke-Git {
    param([string[]]$Argumentos)
    & git -C $raiz @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw ('Falha ao executar: git ' + ($Argumentos -join ' '))
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git nao foi encontrado. Instale o Git for Windows e tente novamente.'
}

$branch = (& git -C $raiz branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or -not $branch) {
    throw 'O repositorio nao esta em uma branch. Saia do estado detached HEAD.'
}

$alteracoes = (& git -C $raiz status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw 'Nao foi possivel consultar o estado do repositorio.'
}
if ($alteracoes) {
    Write-Host 'A sincronizacao foi interrompida: ha alteracoes sem commit.' -ForegroundColor Yellow
    & git -C $raiz status --short
    throw 'Revise o diff, execute os testes e crie o commit conscientemente antes de sincronizar.'
}

Invoke-Git -Argumentos @('fetch', 'origin')
Invoke-Git -Argumentos @('pull', '--rebase', 'origin', $branch)
Invoke-Git -Argumentos @('push', '--set-upstream', 'origin', $branch)

Write-Host ('Branch ' + $branch + ' sincronizada com o GitHub.') -ForegroundColor Green
