[CmdletBinding()]
param(
    [string]$ProjectId = "6a8dc7b2da2512458af80763",
    [string]$Mensagem,
    [switch]$Validar
)

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
$origem = Join-Path $raiz "overlief\artigo_revista_unificado"
$pastaEspelhos = Join-Path ([IO.Path]::GetTempPath()) 'tcc-overleaf-sync'
$espelho = Join-Path $pastaEspelhos $ProjectId
$urlProjeto = "https://www.overleaf.com/project/$ProjectId"
$urlGit = "https://git.overleaf.com/$ProjectId"

function Invoke-Git {
    param(
        [string]$Diretorio,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Argumentos
    )
    & git -C $Diretorio @Argumentos
    if ($LASTEXITCODE -ne 0) {
        throw ('O comando Git falhou: ' + ($Argumentos -join ' '))
    }
}

function Assert-EspelhoSeguro {
    $raizCompleta = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
    $espelhoCompleto = [IO.Path]::GetFullPath($espelho).TrimEnd('\')
    $prefixo = $raizCompleta + '\tcc-overleaf-sync\'
    if (-not $espelhoCompleto.StartsWith($prefixo, [StringComparison]::OrdinalIgnoreCase)) {
        throw ('Diretorio de sincronizacao inseguro: ' + $espelhoCompleto)
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git nao foi encontrado. Instale o Git for Windows.'
}
if (-not (Get-Command robocopy -ErrorAction SilentlyContinue)) {
    throw 'Robocopy nao foi encontrado nesta instalacao do Windows.'
}
if (-not (Test-Path -LiteralPath $origem -PathType Container)) {
    throw ('A pasta do artigo nao foi encontrada: ' + $origem)
}
if ($ProjectId -notmatch '^[a-zA-Z0-9]+$') {
    throw 'O identificador do projeto Overleaf e invalido.'
}

Assert-EspelhoSeguro

if ($Validar) {
    Write-Host 'Configuracao valida.' -ForegroundColor Green
    Write-Host ('Origem:   ' + $origem)
    Write-Host ('Espelho:  ' + $espelho)
    Write-Host ('Overleaf: ' + $urlProjeto)
    exit 0
}

Write-Host 'Sincronizando somente o artigo de revista...' -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath (Join-Path $espelho '.git') -PathType Container)) {
    New-Item -ItemType Directory -Path $pastaEspelhos -Force | Out-Null
    Write-Host 'Primeiro acesso: use git como usuario e o token do Overleaf como senha.'
    & git clone $urlGit $espelho
    if ($LASTEXITCODE -ne 0) {
        throw 'Nao foi possivel acessar o projeto. Confirme o token e o acesso Premium.'
    }
    Invoke-Git -Diretorio $espelho -Argumentos @('config', 'user.name', 'Sincronizador do TCC')
    Invoke-Git -Diretorio $espelho -Argumentos @('config', 'user.email', 'overleaf-sync@users.noreply.github.com')
}
else {
    $branch = (& git -C $espelho branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $branch) {
        throw ('Nao foi possivel identificar a branch do espelho: ' + $espelho)
    }
    Invoke-Git -Diretorio $espelho -Argumentos @('fetch', 'origin', $branch)
    Invoke-Git -Diretorio $espelho -Argumentos @('reset', '--hard', ('origin/' + $branch))
    Invoke-Git -Diretorio $espelho -Argumentos @('clean', '-fd')
}

$ignorados = @(
    '*.aux', '*.bbl', '*.bcf', '*.blg', '*.fdb_latexmk', '*.fls',
    '*.lof', '*.log', '*.lot', '*.out', '*.run.xml', '*.synctex.gz',
    '*.toc', 'main.pdf'
)
$opcoes = @(
    $origem, $espelho, '/MIR', '/XD', '.git', '/XF'
) + $ignorados + @('/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')

& robocopy @opcoes
$codigoRobocopy = $LASTEXITCODE
if ($codigoRobocopy -ge 8) {
    throw ('Falha ao preparar os arquivos. Codigo Robocopy: ' + $codigoRobocopy)
}

Invoke-Git -Diretorio $espelho -Argumentos @('add', '-A')
& git -C $espelho diff --cached --quiet
$haAlteracoes = $LASTEXITCODE -ne 0
if (-not $haAlteracoes) {
    Write-Host 'O Overleaf ja esta atualizado.' -ForegroundColor Green
    Write-Host $urlProjeto
    exit 0
}

if (-not $Mensagem) {
    $momento = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $Mensagem = 'Atualizacao do artigo - ' + $momento
}

Invoke-Git -Diretorio $espelho -Argumentos @('commit', '-m', $Mensagem)
Invoke-Git -Diretorio $espelho -Argumentos @('push', 'origin', 'HEAD')

Write-Host 'Artigo publicado no Overleaf.' -ForegroundColor Green
Write-Host $urlProjeto
