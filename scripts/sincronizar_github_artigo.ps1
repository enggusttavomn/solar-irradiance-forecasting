[CmdletBinding()]
param(
    [string]$Mensagem,
    [switch]$Validar
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$artigoRelativo = 'overlief/artigo_revista_unificado'

function Invoke-GitRaiz {
    param([string[]]$Argumentos)
    & git -C $raiz @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw ('O comando GitHub falhou: git ' + ($Argumentos -join ' '))
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git nao foi encontrado.'
}

$branch = (& git -C $raiz branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or -not $branch) {
    throw 'O repositorio principal nao esta em uma branch.'
}

if ($Validar) {
    Write-Host ('Branch GitHub: ' + $branch)
    Write-Host ('Pasta monitorada: ' + $artigoRelativo)
    exit 0
}

# Marca arquivos novos sem preparar mudancas de outras pastas.
Invoke-GitRaiz -Argumentos @('add', '-N', '--', $artigoRelativo)

& git -C $raiz diff --quiet -- $artigoRelativo
$alteradoNoTrabalho = $LASTEXITCODE -ne 0
& git -C $raiz diff --cached --quiet -- $artigoRelativo
$alteradoNoIndice = $LASTEXITCODE -ne 0

if (-not $alteradoNoTrabalho -and -not $alteradoNoIndice) {
    Write-Host 'A pasta do artigo ja esta atualizada no GitHub.'
    exit 0
}

if (-not $Mensagem) {
    $Mensagem = 'Atualizacao automatica do artigo - ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
}

# O pathspec faz o commit somente desta pasta e preserva o restante do indice.
Invoke-GitRaiz -Argumentos @('commit', '--only', '-m', $Mensagem, '--', $artigoRelativo)
Invoke-GitRaiz -Argumentos @('push', 'origin', 'HEAD')

Write-Host ('Artigo enviado ao GitHub na branch ' + $branch + '.')
