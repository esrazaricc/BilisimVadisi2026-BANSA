$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -X utf8 .\scripts\run_tom_product_identity_hotfix_v1.py
if ($LASTEXITCODE -ne 0) { throw "TOM product identity hotfix failed. ExitCode=$LASTEXITCODE" }
