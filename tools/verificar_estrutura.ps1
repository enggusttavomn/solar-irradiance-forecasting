# Parametro opcional: por padrao, a raiz e a pasta acima de ``tools``.
param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

# Lista dos arquivos e diretorios minimos para considerar o projeto completo.
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

# Acumula todos os itens ausentes para exibi-los de uma vez ao usuario.
$missing = @()
foreach ($path in $requiredPaths) {
    # ``Join-Path`` monta caminhos validos sem concatenar separadores manualmente.
    $fullPath = Join-Path $ProjectRoot $path
    if (-not (Test-Path $fullPath)) {
        $missing += $path
    }
}

# Codigo de saida 1 sinaliza falha para terminais e ferramentas de automacao.
if ($missing.Count -gt 0) {
    Write-Host "Estrutura incompleta:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

# Codigo 0 indica que todos os caminhos obrigatorios foram encontrados.
Write-Host "Estrutura principal OK." -ForegroundColor Green
exit 0
