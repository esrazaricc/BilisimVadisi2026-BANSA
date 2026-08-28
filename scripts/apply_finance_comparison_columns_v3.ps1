$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$env:PYTHONUTF8 = "1"

Write-Host "[1/3] Kategoriye ozel finansman sutun profilleri denetleniyor..."
python .\scripts\audit_finance_comparison_columns.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/3] Hedef testler calistiriliyor..."
python -m pytest -q `
    tests\test_finance_column_profiles.py `
    tests\test_finance_scope_hierarchy.py `
    tests\test_finance_taxonomy.py `
    tests\test_pricing_evidence_guardrails.py `
    tests\test_housing_finance_audit_v2.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/3] Tamamlandi. PostgreSQL verisi degistirilmedi; ana karsilastirma tablosu kategoriye ozel sutun politikasina gecti."
Write-Host "PASS"
