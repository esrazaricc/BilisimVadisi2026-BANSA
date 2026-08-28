$ErrorActionPreference = "Stop"
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $project
$env:PYTHONPATH = $project
$python = "python"

function Invoke-Step {
    param(
        [string]$Label,
        [string[]]$PythonArgs
    )
    Write-Host "`n$Label" -ForegroundColor Cyan
    & $python @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "$Label basarisiz oldu. ExitCode=$LASTEXITCODE"
    }
}

try {
    Invoke-Step "[1/11] BDDK 10 banka kapsami ve kalan 5 banka config audit..." @(
        "-X", "utf8", ".\scripts\audit_remaining_banks_finance_integration_v1.py"
    )

    Invoke-Step "[2/11] Entegrasyon / halusinasyon guardrail testleri..." @(
        "-X", "utf8", "-m", "pytest", "-q",
        "tests\test_remaining_banks_finance_integration_v1.py",
        "tests\test_finance_data_accuracy_v2.py",
        "tests\test_finance_taxonomy.py",
        "tests\test_finance_scope_hierarchy.py",
        "tests\test_finance_column_profiles.py",
        "tests\test_pricing_evidence_guardrails.py",
        "tests\test_vehicle_rule_parser.py"
    )

    Invoke-Step "[3/11] Adil + TOM + Emlak + Vakif + Ziraat resmi finansman sayfalari taraniyor..." @(
        "-X", "utf8", ".\scripts\run_remaining_banks_finance_integration_v1.py"
    )

    Invoke-Step "[4/11] Canonical veri / halusinasyon guardrail'leri SQLite'a uygulanıyor..." @(
        "-X", "utf8", ".\scripts\apply_finance_data_accuracy_v2.py"
    )

    Invoke-Step "[5/11] Finansman rule/evidence tablolari yeniden senkronize ediliyor..." @(
        "-X", "utf8", ".\scripts\sync_finance_rule_engine.py"
    )

    Invoke-Step "      Mevcut urun-ozel semantik duzeltmeler korunuyor..." @(
        "-X", "utf8", ".\scripts\apply_finance_semantic_fixes_v3.py"
    )

    Invoke-Step "[6/11] Kalan 5 banka canli SQLite audit..." @(
        "-X", "utf8", ".\scripts\audit_remaining_banks_finance_integration_v1.py", "--sqlite"
    )

    Invoke-Step "[7/11] Kapsam/taksonomi ve kategori sutun auditleri..." @(
        "-X", "utf8", ".\scripts\audit_finance_scope_and_taxonomy.py"
    )
    Invoke-Step "      Kategoriye ozel sutun audit..." @(
        "-X", "utf8", ".\scripts\audit_finance_comparison_columns.py"
    )
    Invoke-Step "      Mevcut finansman veri dogruluk regresyon audit..." @(
        "-X", "utf8", ".\scripts\audit_finance_data_accuracy_v2.py"
    )
    Invoke-Step "      Mevcut tablo dogruluk regresyon audit..." @(
        "-X", "utf8", ".\scripts\audit_finance_table_accuracy_v3.py"
    )

    Write-Host "`n[8/11] PostgreSQL canli finansman verisi guncellenecek." -ForegroundColor Cyan
    $secure = Read-Host "PostgreSQL postgres parolasi" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $encoded = [uri]::EscapeDataString($plain)
        $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

        Invoke-Step "[9/11] PostgreSQL'e BDDK 10 banka kapsami upsert ediliyor..." @(
            "-X", "utf8", ".\scripts\ensure_finance_banks_postgresql.py"
        )

        Invoke-Step "[10/11] Dogrulanmis SQLite finansmanlari PostgreSQL'e aktariliyor..." @(
            "-X", "utf8", ".\scripts\sync_finance_data_accuracy_v2_to_postgresql.py"
        )

        Invoke-Step "[11/11] 10 banka SQLite + PostgreSQL entegrasyon audit..." @(
            "-X", "utf8", ".\scripts\audit_remaining_banks_finance_integration_v1.py", "--sqlite", "--postgres"
        )
    }
    finally {
        if ($ptr) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
        Remove-Variable secure, ptr, plain, encoded -ErrorAction SilentlyContinue
        Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
    }

    Write-Host "`nKALAN BANKALAR FINANSMAN ENTEGRASYONU V1 TAMAMLANDI" -ForegroundColor Green
    Write-Host "PASS" -ForegroundColor Green
    Write-Host "Uygulamayi acmak icin: .\scripts\run_streamlit_postgresql.ps1"
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
