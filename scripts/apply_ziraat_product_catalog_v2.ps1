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
    Invoke-Step "[1/7] Ziraat katalog V2 offline testleri..." @(
        "-X", "utf8", "-m", "pytest", "-q",
        "tests\test_ziraat_product_catalog_v2.py",
        "tests\test_finance_data_accuracy_v2.py",
        "tests\test_finance_taxonomy.py",
        "tests\test_finance_scope_hierarchy.py",
        "tests\test_finance_column_profiles.py",
        "tests\test_pricing_evidence_guardrails.py",
        "tests\test_vehicle_rule_parser.py"
    )

    Invoke-Step "[2/7] Resmi Ziraat urun katalog config audit..." @(
        "-X", "utf8", ".\scripts\audit_ziraat_product_catalog_v2.py"
    )

    Invoke-Step "[3/7] Ziraat canli tarama + SQLite generic temizlik + rule sync..." @(
        "-X", "utf8", ".\scripts\run_ziraat_product_catalog_v2.py"
    )

    Invoke-Step "[4/7] Ziraat canli SQLite katalog audit..." @(
        "-X", "utf8", ".\scripts\audit_ziraat_product_catalog_v2.py", "--sqlite"
    )

    Write-Host "`n[5/7] PostgreSQL Ziraat katalog senkronu hazirlaniyor." -ForegroundColor Cyan
    $secure = Read-Host "PostgreSQL postgres parolasi" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $encoded = [uri]::EscapeDataString($plain)
        $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

        Invoke-Step "[5/7] Dogrulanmis SQLite finansmanlari PostgreSQL'e aktariliyor..." @(
            "-X", "utf8", ".\scripts\sync_finance_data_accuracy_v2_to_postgresql.py"
        )

        Invoke-Step "[6/7] Eski generic Ziraat PostgreSQL urunleri pasife aliniyor..." @(
            "-X", "utf8", ".\scripts\cleanup_ziraat_generic_products_v2.py", "--postgres-only"
        )

        Invoke-Step "[7/7] Ziraat SQLite + PostgreSQL final katalog audit..." @(
            "-X", "utf8", ".\scripts\audit_ziraat_product_catalog_v2.py", "--sqlite", "--postgres"
        )
    }
    finally {
        if ($ptr) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        Remove-Variable secure, ptr, plain, encoded -ErrorAction SilentlyContinue
        Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
    }

    Write-Host "`nZIRAAT URUN KATALOG V2 TAMAMLANDI" -ForegroundColor Green
    Write-Host "PASS" -ForegroundColor Green
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
