$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "BANSA Finansman Alanı hiyerarşisi V2 kontrol ediliyor..." -ForegroundColor Cyan

$page = Get-ChildItem -Path (Join-Path $ProjectRoot "pages") -Filter "4_Finansman_*.py" |
    Where-Object { $_.Name -notmatch '#U[0-9A-Fa-f]{4}' } |
    Select-Object -First 1

if (-not $page) {
    throw "Finansman Karşılaştırması sayfası bulunamadı."
}

Write-Host ("Finansman sayfası: " + $page.Name) -ForegroundColor DarkGray

python -m py_compile $page.FullName
python -m py_compile (Join-Path $ProjectRoot "src\finance_taxonomy.py")
python -m pytest -q `
    tests/test_finance_taxonomy.py `
    tests/test_finance_scope_hierarchy.py

python scripts/audit_finance_scope_and_taxonomy.py

Write-Host "" 
Write-Host "PASS - Finansman Alanı -> Finansman Türü -> Bankalar hiyerarşisi hazır." -ForegroundColor Green
Write-Host "Veritabanı değiştirilmedi; mevcut scope ve ürün aileleri kullanılıyor." -ForegroundColor DarkGray
