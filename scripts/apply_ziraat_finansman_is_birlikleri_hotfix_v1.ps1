$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "[1/2] Ziraat Finansman Is Birlikleri URL testi..."
python -X utf8 -m pytest -q tests\test_ziraat_finansman_is_birlikleri_url.py
if ($LASTEXITCODE -ne 0) { throw "Ziraat URL testi basarisiz oldu. ExitCode=$LASTEXITCODE" }
Write-Host "[2/2] Ziraat Katilim canli taramasi..."
python -X utf8 .\scripts\run_standard_products_live_update.py --bank "Ziraat Katılım"
if ($LASTEXITCODE -ne 0) { throw "Ziraat Katilim canli taramasi basarisiz oldu. ExitCode=$LASTEXITCODE" }
Write-Host "PASS - Ziraat Finansman Is Birlikleri yolu guncellendi ve canli tarama tamamlandi."
