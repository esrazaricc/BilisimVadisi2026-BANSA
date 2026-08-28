$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$pythonCandidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "python"
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if ($candidate -eq "python") {
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($command) {
            $python = "python"
            break
        }
    }
    elseif (Test-Path $candidate) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    throw "Python bulunamadı. Python 3.12 kurulumunu veya PATH ayarını kontrol edin."
}

$secure = Read-Host "PostgreSQL postgres parolası" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)

try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $encoded = [uri]::EscapeDataString($plain)
    $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

    Write-Host "Konut finansmanı düzeltmesi PostgreSQL'e uygulanıyor..." -ForegroundColor Cyan
    & $python .\scripts\repair_housing_finance_comparison_v2.py
    if ($LASTEXITCODE -ne 0) {
        throw "Repair scripti hata kodu ile kapandı: $LASTEXITCODE"
    }

    Write-Host "Konut karşılaştırma audit'i çalıştırılıyor..." -ForegroundColor Cyan
    & $python .\scripts\audit_housing_finance_comparison_v2.py
    if ($LASTEXITCODE -ne 0) {
        throw "Audit başarısız oldu: $LASTEXITCODE"
    }

    Write-Host "Tamamlandı. Uygulamayı yeniden açabilirsiniz." -ForegroundColor Green
}
finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    Remove-Variable secure, ptr -ErrorAction SilentlyContinue
    Remove-Variable plain, encoded -ErrorAction SilentlyContinue
    Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
}
