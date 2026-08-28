$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "BANSA Finansman Taksonomisi V1 kontrol ediliyor..." -ForegroundColor Cyan

# Windows PowerShell 5.1 may misread UTF-8 filenames containing Turkish characters
# when a .ps1 file has no BOM. Resolve the finance page with an ASCII-only pattern
# instead of hard-coding the Turkish filename in this script.
$FinancePages = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "pages") -Filter "4_Finansman_*.py" -File)
if ($FinancePages.Count -ne 1) {
    Write-Host "HATA - pages klasorunde 4_Finansman_*.py desenine uyan tam olarak 1 dosya bekleniyordu." -ForegroundColor Red
    Write-Host "Bulunan dosya sayisi: $($FinancePages.Count)" -ForegroundColor Red
    if ($FinancePages.Count -gt 0) {
        $FinancePages | ForEach-Object { Write-Host " - $($_.Name)" }
    }
    exit 1
}
$FinancePage = $FinancePages[0].FullName
Write-Host "Finansman sayfasi: $($FinancePages[0].Name)" -ForegroundColor DarkGray

python -m py_compile "src\finance_taxonomy.py" $FinancePage "scripts\audit_finance_scope_and_taxonomy.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python -m pytest "tests\test_finance_taxonomy.py" "tests\test_pricing_evidence_guardrails.py" "tests\test_housing_finance_audit_v2.py" -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

python "scripts\audit_finance_scope_and_taxonomy.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "PASS - Taksonomi ve BDDK banka kapsami hazir." -ForegroundColor Green
Write-Host "PostgreSQL verisi bu adimda degistirilmedi. Uygulamayi yeniden baslatabilirsiniz." -ForegroundColor Green
