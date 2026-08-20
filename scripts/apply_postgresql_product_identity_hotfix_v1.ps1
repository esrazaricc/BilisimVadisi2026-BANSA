$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $project
$env:PYTHONPATH = $project
$python = "python"

function Invoke-Step {
    param([string]$Label,[string[]]$PythonArgs)
    Write-Host "`n$Label" -ForegroundColor Cyan
    & $python @PythonArgs
    if ($LASTEXITCODE -ne 0) { throw "$Label basarisiz oldu. ExitCode=$LASTEXITCODE" }
}

try {
    Invoke-Step "[1/3] PostgreSQL urun kimligi hotfix testi..." @(
        "-X","utf8","-m","pytest","-q","tests\test_postgresql_standard_product_identity_hotfix_v1.py"
    )

    Write-Host "`n[2/3] Dogrulanmis SQLite finansmanlari PostgreSQL'e yeniden senkronize edilecek." -ForegroundColor Cyan
    $secure = Read-Host "PostgreSQL postgres parolasi" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $encoded = [uri]::EscapeDataString($plain)
        $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

        Invoke-Step "      PostgreSQL kimlik uzlastirmali finansman senkronu..." @(
            "-X","utf8",".\scripts\sync_finance_data_accuracy_v2_to_postgresql.py"
        )

        Invoke-Step "[3/3] 10 banka SQLite + PostgreSQL final entegrasyon audit..." @(
            "-X","utf8",".\scripts\audit_remaining_banks_finance_integration_v1.py","--sqlite","--postgres"
        )
    }
    finally {
        if ($ptr) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        Remove-Variable secure, ptr, plain, encoded -ErrorAction SilentlyContinue
        Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
    }

    Write-Host "`nPOSTGRESQL URUN KIMLIGI HOTFIX V1 TAMAMLANDI" -ForegroundColor Green
    Write-Host "PASS" -ForegroundColor Green
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
