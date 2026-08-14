param(
    [string]$ProjectPath = "C:\Users\Esra\Desktop\bansa_project1",
    [int]$EveryHours = 1
)

$ErrorActionPreference = "Stop"
if ($EveryHours -lt 1) {
    throw "En sık çalışma aralığı 1 saattir."
}

$ProjectPath = (Resolve-Path $ProjectPath).Path
$Python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$Script = Join-Path $ProjectPath "scripts\run_all_banks_live_update.py"
$TaskName = "BANSA_TumBankalar_CanliGuncelleme"

if (-not (Test-Path $Python)) {
    throw "Python 3.12 bulunamadı: $Python"
}
if (-not (Test-Path $Script)) {
    throw "Güncelleme scripti bulunamadı: $Script"
}

$TaskCommand = '"' + $Python + '" -X utf8 "' + $Script + '"'

& schtasks.exe /Create `
    /TN $TaskName `
    /TR $TaskCommand `
    /SC HOURLY `
    /MO $EveryHours `
    /F

if ($LASTEXITCODE -ne 0) {
    throw "Windows zamanlanmış görevi oluşturulamadı."
}

Write-Host "Görev oluşturuldu: $TaskName"
Write-Host "Aralık: her $EveryHours saat"
Write-Host "Proje: $ProjectPath"
