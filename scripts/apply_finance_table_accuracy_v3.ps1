$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = $ProjectRoot

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        throw "Python bulunamadi. Python 3.12 veya proje Python ortamini kontrol edin."
    }
    $python = $cmd.Source
}

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
    Invoke-Step "[1/10] Urun-ozel canonical veri kurallari SQLite'a uygulanıyor..." @(
        ".\scripts\apply_finance_data_accuracy_v2.py"
    )

    Invoke-Step "[2/10] Finansman kural/evidence tablolari yeniden senkronize ediliyor..." @(
        ".\scripts\sync_finance_rule_engine.py"
    )

    # Bu adim rule sync'ten SONRA gelmeli. Aksi halde doğrulanmış semantik
    # ürün özellikleri generic extractor çıktısıyla tekrar ezilebilir.
    Invoke-Step "[3/10] Urun-ozel semantik ve kaynak duzeltmeleri uygulanıyor..." @(
        ".\scripts\apply_finance_semantic_fixes_v3.py"
    )

    Invoke-Step "[4/10] Finansman Tablo Dogruluk V3 SQLite audit calisiyor..." @(
        ".\scripts\audit_finance_table_accuracy_v3.py"
    )

    Invoke-Step "      Evidence / fiyatlama guardrail audit..." @(
        ".\scripts\audit_finance_data_accuracy_v2.py"
    )

    Invoke-Step "[5/10] Konut + kapsam/taksonomi + sutun regresyon auditleri..." @(
        ".\scripts\audit_housing_finance_comparison_v2.py"
    )
    Invoke-Step "      BDDK kapsam/taksonomi audit..." @(
        ".\scripts\audit_finance_scope_and_taxonomy.py"
    )
    Invoke-Step "      Kategoriye ozel sutun audit..." @(
        ".\scripts\audit_finance_comparison_columns.py"
    )

    Invoke-Step "[6/10] Hedef regresyon testleri calisiyor..." @(
        "-m", "pytest", "-q",
        "tests\test_finance_data_accuracy_v2.py",
        "tests\test_vehicle_rule_parser.py",
        "tests\test_finance_taxonomy.py",
        "tests\test_finance_scope_hierarchy.py",
        "tests\test_finance_column_profiles.py",
        "tests\test_pricing_evidence_guardrails.py",
        "tests\test_housing_finance_audit_v2.py"
    )

    Write-Host "`n[7/10] PostgreSQL canli verisi senkronize edilecek." -ForegroundColor Cyan
    $secure = Read-Host "PostgreSQL postgres parolasi" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        $encoded = [uri]::EscapeDataString($plain)
        $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"

        Invoke-Step "[8/10] SQLite dogrulanmis finansman verisi PostgreSQL'e aktariliyor..." @(
            ".\scripts\sync_finance_data_accuracy_v2_to_postgresql.py"
        )

        Invoke-Step "[9/10] SQLite + PostgreSQL Finansman Tablo Dogruluk V3 audit..." @(
            ".\scripts\audit_finance_table_accuracy_v3.py"
        )

        Invoke-Step "      PostgreSQL evidence / guardrail audit..." @(
            ".\scripts\audit_finance_data_accuracy_v2.py"
        )
    }
    finally {
        if ($ptr) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
        Remove-Variable secure, ptr, plain, encoded -ErrorAction SilentlyContinue
        Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
    }

    Write-Host "`n[10/10] Finansman Tablo Dogruluk V3 tamamlandi." -ForegroundColor Green
    Write-Host "PASS" -ForegroundColor Green
    Write-Host "Uygulamayi acmak icin: .\scripts\run_streamlit_postgresql.ps1"
}
finally {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
