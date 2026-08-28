$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $project
$env:PYTHONPATH = $project
$python = "python"

function Invoke-Step {
    param([string]$Label, [string[]]$PythonArgs)
    Write-Host "`n$Label" -ForegroundColor Cyan
    & $python @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Label basarisiz oldu. ExitCode=$LASTEXITCODE"
    }
}

try {
    Invoke-Step "[1/5] Ziraat detail/katalog fallback testleri..." @(
        "-X", "utf8", "-m", "pytest", "-q",
        "tests\test_ziraat_covered_detail_errors_v2_1.py",
        "tests\test_ziraat_product_catalog_v2.py"
    )

    Invoke-Step "[2/5] Ziraat canli katalog tarama + generic temizlik + rule sync..." @(
        "-X", "utf8", ".\scripts\run_ziraat_product_catalog_v2.py"
    )

    Invoke-Step "[3/5] Ziraat SQLite katalog audit..." @(
        "-X", "utf8", ".\scripts\audit_ziraat_product_catalog_v2.py", "--sqlite"
    )

    Write-Host "`n[4/5] PostgreSQL Ziraat katalog senkronu hazirlaniyor." -ForegroundColor Cyan
    $secure = Read-Host "PostgreSQL postgres parolasi" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $encoded = [uri]::EscapeDataString($plain)
        $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

        Invoke-Step "[4/5] Dogrulanmis SQLite finansmanlari PostgreSQL'e aktariliyor..." @(
            "-X", "utf8", ".\scripts\sync_finance_data_accuracy_v2_to_postgresql.py"
        )

        Invoke-Step "[4/5] Eski generic Ziraat PostgreSQL urunleri pasife aliniyor..." @(
            "-X", "utf8", ".\scripts\cleanup_ziraat_generic_products_v2.py", "--postgres-only"
        )

        Invoke-Step "[5/5] Ziraat SQLite + PostgreSQL final katalog audit..." @(
            "-X", "utf8", ".\scripts\audit_ziraat_product_catalog_v2.py", "--sqlite", "--postgres"
        )
    }
    finally {
        if ($ptr) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        Remove-Variable secure, ptr, plain, encoded -ErrorAction SilentlyContinue
        Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
    }

    Write-Host "`nZIRAAT URUN KATALOG V2.1 TAMAMLANDI" -ForegroundColor Green
    Write-Host "PASS" -ForegroundColor Green
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
