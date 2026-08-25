$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git nao foi encontrado. Instale o Git for Windows e tente novamente."
}

git add -A
git diff --cached --quiet

if ($LASTEXITCODE -ne 0) {
    $momento = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    git commit -m "Atualizacao local - $momento"
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel criar o commit." }
}
else {
    Write-Host "Nenhuma alteracao nova para registrar."
}

git pull --rebase origin main
if ($LASTEXITCODE -ne 0) { throw "O pull encontrou um problema. Resolva-o antes de enviar." }

git push origin main
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel enviar as alteracoes ao GitHub." }

Write-Host "Projeto sincronizado com o GitHub." -ForegroundColor Green

