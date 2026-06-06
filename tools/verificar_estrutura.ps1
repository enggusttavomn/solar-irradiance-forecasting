param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$requiredPaths = @(
    "README.md",
    "requirements.txt",
    ".gitignore",
    "treinamento_principal.py",
    "treinar_todas_localidades.py",
    "codigo_fonte",
    "codigo_fonte\preprocessamento.py",
    "codigo_fonte\features.py",
    "codigo_fonte\modelos.py",
    "codigo_fonte\avaliacao.py",
    "codigo_fonte\graficos.py",
    "dados\brutos\localidades_ev",
    "dados\processados",
    "cadernos_jupyter",
    "relatorios",
    "testes",
    "tools"
)

$missing = @()
foreach ($path in $requiredPaths) {
    $fullPath = Join-Path $ProjectRoot $path
    if (-not (Test-Path $fullPath)) {
        $missing += $path
    }
}

if ($missing.Count -gt 0) {
    Write-Host "Estrutura incompleta:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "Estrutura principal OK." -ForegroundColor Green
exit 0
