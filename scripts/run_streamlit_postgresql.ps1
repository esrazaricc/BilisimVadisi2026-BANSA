$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    throw "Python bulunamadı: $python"
}

$secure = Read-Host "PostgreSQL postgres parolası" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)

try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $encoded = [uri]::EscapeDataString($plain)
    $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

    Write-Host "PostgreSQL bağlantısı bu oturum için hazırlandı." -ForegroundColor Green
    & $python -m streamlit run .\Ana_Sayfa.py
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Variable secure, ptr -ErrorAction SilentlyContinue
    Remove-Variable plain, encoded -ErrorAction SilentlyContinue
    Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
}
