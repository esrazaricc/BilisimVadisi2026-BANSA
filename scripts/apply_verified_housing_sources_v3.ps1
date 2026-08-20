$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$secure = Read-Host "PostgreSQL postgres parolası" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)

try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $encoded = [uri]::EscapeDataString($plain)
    $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

    Write-Host "1/4 Konut finansmanı doğrulanmış kaynak düzeltmeleri uygulanıyor..." -ForegroundColor Cyan
    & $python .\scripts\repair_housing_finance_comparison_v2.py
    if ($LASTEXITCODE -ne 0) {
        throw "Konut finansmanı repair başarısız oldu. Exit code: $LASTEXITCODE"
    }

    Write-Host "2/4 Örnek/temsili fiyat guardrail temizliği uygulanıyor..." -ForegroundColor Cyan
    & $python .\scripts\repair_misleading_example_pricing.py
    if ($LASTEXITCODE -ne 0) {
        throw "Fiyatlama guardrail temizliği başarısız oldu. Exit code: $LASTEXITCODE"
    }

    Write-Host "3/4 SQLite + UI audit çalışıyor..." -ForegroundColor Cyan
    & $python .\scripts\audit_housing_finance_comparison_v2.py
    if ($LASTEXITCODE -ne 0) {
        throw "SQLite/UI audit başarısız oldu. Exit code: $LASTEXITCODE"
    }

    Write-Host "4/4 Canlı PostgreSQL audit çalışıyor..." -ForegroundColor Cyan
    & $python .\scripts\audit_housing_finance_postgresql_v3.py
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL audit başarısız oldu. Exit code: $LASTEXITCODE"
    }

    Write-Host "Tüm doğrulanmış konut finansmanı düzeltmeleri başarıyla uygulandı." -ForegroundColor Green
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Variable secure, ptr -ErrorAction SilentlyContinue
    Remove-Variable plain, encoded -ErrorAction SilentlyContinue
    Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
}
