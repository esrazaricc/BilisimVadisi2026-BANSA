$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = $null

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
}

if (-not $python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $python = $pythonCommand.Source
    }
}

if (-not $python) {
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        $python = $pyCommand.Source
    }
}

if (-not $python) {
    throw "Python bulunamadi. Once Python 3.11+ veya .venv kurun."
}

$createdDsn = $false
$ptr = [IntPtr]::Zero

try {
    if ([string]::IsNullOrWhiteSpace($env:POSTGRES_DSN)) {
        $secure = Read-Host "PostgreSQL postgres parolasi" -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)

        if ([string]::IsNullOrWhiteSpace($plain)) {
            throw "Parola bos girildi."
        }

        $encoded = [uri]::EscapeDataString($plain)
        $env:POSTGRES_DSN = "postgresql://postgres:$encoded@127.0.0.1:5432/bansa_db"
        $createdDsn = $true
    }

    Write-Host "BANSA dashboard baslatiliyor..." -ForegroundColor Green
    & $python -m streamlit run .\Ana_Sayfa.py
}
finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }

    Remove-Variable secure, plain, encoded, ptr -ErrorAction SilentlyContinue

    if ($createdDsn) {
        Remove-Item Env:POSTGRES_DSN -ErrorAction SilentlyContinue
    }
}
