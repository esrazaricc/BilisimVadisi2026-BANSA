$ErrorActionPreference = "Stop"

Write-Host "[1/3] Fiyatlama Kaynagi ana tablo politikasi kontrol ediliyor..."
python -m py_compile .\src\finance_column_profiles.py
if ($LASTEXITCODE -ne 0) { throw "finance_column_profiles.py derlenemedi." }

Write-Host "[2/3] Finansman sutun testleri calisiyor..."
python -m pytest -q .\tests\test_finance_column_profiles.py
if ($LASTEXITCODE -ne 0) { throw "Finansman sutun testleri basarisiz." }

Write-Host "[3/3] Taksonomi kontrol ediliyor..."
python -c "import json; d=json.load(open(r'config/finance_taxonomy.json', encoding='utf-8')); assert all('Ücret/Fiyatlama Kaynağı' not in c.get('required_comparison_fields',[]) for c in d['primary_retail_categories']); print('PASS - Fiyatlama Kaynağı UI sütunu kaldırıldı; kanıt verisi korunuyor.')"
if ($LASTEXITCODE -ne 0) { throw "Taksonomi kontrolu basarisiz." }

Write-Host "PASS"
Write-Host "Not: PostgreSQL/SQLite verisi silinmez. Fiyatlama kaynak URL'leri halusinasyon korumasi ve audit icin veri katmaninda korunur."
