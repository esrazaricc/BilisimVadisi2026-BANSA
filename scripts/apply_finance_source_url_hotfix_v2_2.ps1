$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Write-Host "[1/2] Kaynak sütunu hotfix kontrolü..."
python "$PSScriptRoot\check_finance_source_url_hotfix_v2_2.py"
if ($LASTEXITCODE -ne 0) { throw "Hotfix kontrolü başarısız oldu." }
Write-Host "[2/2] Python sözdizimi kontrolü..."
$FinancePage = Get-ChildItem -Path "$Root\pages" -Filter "4_Finansman_*.py" | Select-Object -First 1
python -m py_compile "$Root\src\postgres_repository.py" $FinancePage.FullName
if ($LASTEXITCODE -ne 0) { throw "Python sözdizimi kontrolü başarısız oldu." }
Write-Host "PASS - Finance source URL hotfix V2.2 hazır."
