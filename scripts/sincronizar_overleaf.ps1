[CmdletBinding()]
param(
    [string]$ProjectId = "6a8dc7b2da2512458af80763",
    [string]$Mensagem,
    [switch]$Validar
)

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
$origem = Join-Path $raiz "artigos\revista_unificado"
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

function Test-PrefixoBytes {
    param(
        [byte[]]$Conteudo,
        [byte[]]$Assinatura
    )

    if ($Conteudo.Length -lt $Assinatura.Length) {
        return $false
    }
    for ($i = 0; $i -lt $Assinatura.Length; $i++) {
        if ($Conteudo[$i] -ne $Assinatura[$i]) {
            return $false
        }
    }
    return $true
}

function Test-AssetsPublicacao {
    param(
        [string]$Diretorio,
        [string[]]$CaminhosIgnorados = @()
    )

    $diretorioCompleto = [IO.Path]::GetFullPath($Diretorio).TrimEnd('\')
    $assinaturaPng = [byte[]](0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
    $assinaturaPdf = [Text.Encoding]::ASCII.GetBytes('%PDF-')
    $assinaturaNasca = [Text.Encoding]::ASCII.GetBytes('<## NASCA DRM FILE - VER1.00 ##>')
    $pdfsNasca = @()

    $assets = Get-ChildItem -LiteralPath $Diretorio -Recurse -File |
        Where-Object { $_.Extension -in '.png', '.pdf' } |
        Sort-Object FullName

    foreach ($asset in $assets) {
        $relativo = $asset.FullName.Substring($diretorioCompleto.Length).TrimStart('\', '/')
        $relativoNormalizado = $relativo.Replace('\', '/')
        if ($CaminhosIgnorados -contains $relativoNormalizado) {
            continue
        }

        $conteudo = [IO.File]::ReadAllBytes($asset.FullName)
        if ($asset.Extension -ieq '.png') {
            if (-not (Test-PrefixoBytes -Conteudo $conteudo -Assinatura $assinaturaPng)) {
                throw ('PNG invalido; publicacao interrompida: ' + $relativoNormalizado)
            }
            continue
        }

        if (Test-PrefixoBytes -Conteudo $conteudo -Assinatura $assinaturaPdf) {
            continue
        }
        if (Test-PrefixoBytes -Conteudo $conteudo -Assinatura $assinaturaNasca) {
            $pdfsNasca += $relativoNormalizado
            continue
        }
        throw ('PDF invalido ou com assinatura desconhecida; publicacao interrompida: ' + $relativoNormalizado)
    }

    return $pdfsNasca
}

function Remove-PdfsNascaDoEspelho {
    param(
        [string]$DiretorioEspelho,
        [string[]]$CaminhosRelativos
    )

    $espelhoCompleto = [IO.Path]::GetFullPath($DiretorioEspelho).TrimEnd('\')
    $prefixoSeguro = $espelhoCompleto + '\'
    $assinaturaNasca = [Text.Encoding]::ASCII.GetBytes('<## NASCA DRM FILE - VER1.00 ##>')

    foreach ($relativo in $CaminhosRelativos) {
        $destino = [IO.Path]::GetFullPath((Join-Path $espelhoCompleto $relativo))
        if (-not $destino.StartsWith($prefixoSeguro, [StringComparison]::OrdinalIgnoreCase)) {
            throw ('Caminho de PDF NASCA fora do espelho seguro: ' + $destino)
        }
        if (-not (Test-Path -LiteralPath $destino -PathType Leaf)) {
            continue
        }

        $conteudo = [IO.File]::ReadAllBytes($destino)
        if (-not (Test-PrefixoBytes -Conteudo $conteudo -Assinatura $assinaturaNasca)) {
            throw ('O PDF a ignorar mudou de assinatura no espelho: ' + $relativo)
        }

        Remove-Item -LiteralPath $destino -Force
        Write-Warning (
            'PDF encapsulado por NASCA DRM omitido da publicacao; ' +
            'a fonte local foi preservada: ' + $relativo
        )
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

$comandoPython = Get-Command python, python3 -ErrorAction SilentlyContinue | Select-Object -First 1
$pythonPublicacao = if ($comandoPython) { $comandoPython.Source } else { $null }
if (-not $pythonPublicacao) {
    $instalacoesPython = Get-ItemProperty -Path @(
        'HKCU:\Software\Python\PythonCore\*\InstallPath',
        'HKLM:\Software\Python\PythonCore\*\InstallPath'
    ) -ErrorAction SilentlyContinue
    $pythonPublicacao = $instalacoesPython |
        Where-Object { $_.ExecutablePath -and (Test-Path -LiteralPath $_.ExecutablePath -PathType Leaf) } |
        Sort-Object ExecutablePath -Descending |
        Select-Object -First 1 -ExpandProperty ExecutablePath
}
if (-not $pythonPublicacao) {
    throw 'Python 3.10 ou superior e necessario para selecionar os fontes do artigo.'
}
$prefixoFontes = Join-Path ([IO.Path]::GetTempPath()) 'tcc-overleaf-fontes-'
$fontesPublicacao = $prefixoFontes + [Guid]::NewGuid().ToString('N')

try {
& $pythonPublicacao (Join-Path $PSScriptRoot 'preparar_overleaf.py') --origem $origem --destino $fontesPublicacao
if ($LASTEXITCODE -ne 0) {
    throw 'Nao foi possivel preparar as dependencias do artigo e suplemento.'
}
$pdfsNasca = @(Test-AssetsPublicacao -Diretorio $fontesPublicacao)
if ($pdfsNasca.Count -gt 0) {
    throw ('Uma figura necessaria esta encapsulada por NASCA DRM: ' + ($pdfsNasca -join ', '))
}

if ($Validar) {
    Write-Host 'Configuracao e assinaturas dos assets validas.' -ForegroundColor Green
    Write-Host ('Origem:   ' + $origem)
    Write-Host ('Espelho:  ' + $espelho)
    Write-Host ('Overleaf: ' + $urlProjeto)
    Write-Host 'Somente dependencias de main.tex e supplementary_material.tex serao publicadas.'
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

$opcoes = @(
    $fontesPublicacao, $espelho, '/MIR', '/XD', '.git',
    '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP'
)

& robocopy @opcoes
$codigoRobocopy = $LASTEXITCODE
if ($codigoRobocopy -ge 8) {
    throw ('Falha ao preparar os arquivos. Codigo Robocopy: ' + $codigoRobocopy)
}

Remove-PdfsNascaDoEspelho -DiretorioEspelho $espelho -CaminhosRelativos $pdfsNasca
$pdfsNascaNoEspelho = @(Test-AssetsPublicacao -Diretorio $espelho)
if ($pdfsNascaNoEspelho.Count -gt 0) {
    throw (
        'O espelho ainda contem PDF encapsulado por NASCA DRM: ' +
        ($pdfsNascaNoEspelho -join ', ')
    )
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

}
finally {
    $fontesCompletas = [IO.Path]::GetFullPath($fontesPublicacao)
    $prefixoCompleto = [IO.Path]::GetFullPath($prefixoFontes)
    if (-not $fontesCompletas.StartsWith($prefixoCompleto, [StringComparison]::OrdinalIgnoreCase)) {
        throw ('Diretorio temporario inseguro: ' + $fontesCompletas)
    }
    if (Test-Path -LiteralPath $fontesCompletas -PathType Container) {
        Remove-Item -LiteralPath $fontesCompletas -Recurse -Force
    }
}
