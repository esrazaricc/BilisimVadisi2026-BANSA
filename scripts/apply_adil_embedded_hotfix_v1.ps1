$ErrorActionPreference = "Stop"

Write-Host "[1/2] Adil Katilim embedded scanner hotfix testi..."
python -X utf8 -m pytest -q tests\test_adil_embedded_section_fallback.py
if ($LASTEXITCODE -ne 0) { throw "Adil embedded scanner testi basarisiz oldu. ExitCode=$LASTEXITCODE" }

Write-Host "[2/2] Adil Katilim canli taramasi..."
python -X utf8 .\scripts\run_standard_products_live_update.py --bank "Adil Katılım"
if ($LASTEXITCODE -ne 0) { throw "Adil Katilim canli taramasi basarisiz oldu. ExitCode=$LASTEXITCODE" }

Write-Host "PASS - Adil Katilim taramasi tamamlandi."
