[CmdletBinding()]
param([string]$ProjectId = '6a8dc7b2da2512458af80763')

$ErrorActionPreference = 'Stop'
$tokenSeguro = Read-Host 'Cole o token do Overleaf' -AsSecureString
$ponteiro = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($tokenSeguro)

try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ponteiro)
    $credencial = @(
        'protocol=https',
        'host=git.overleaf.com',
        'username=git',
        ('password=' + $token),
        ''
    ) -join "`n"

    $credencial | git credential approve
    if ($LASTEXITCODE -ne 0) {
        throw 'O Git Credential Manager nao conseguiu salvar o token.'
    }
}
finally {
    if ($ponteiro -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ponteiro)
    }
    $token = $null
    $credencial = $null
}

$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'Never'
& git ls-remote ('https://git.overleaf.com/' + $ProjectId) HEAD | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'O token foi salvo, mas o Overleaf recusou a autenticacao.'
}

Write-Host 'Token salvo com seguranca no Git Credential Manager.' -ForegroundColor Green
