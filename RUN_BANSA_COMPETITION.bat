@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo BANSA COMPETITION MODE
echo ================================================================
echo.

set BANSA_LOCAL_AGENT_ENABLED=1
set BANSA_LOCAL_LLM_BASE_URL=http://127.0.0.1:8000/v1
set BANSA_LOCAL_LLM_MODEL=bansa-qwen-local
set BANSA_LOCAL_LLM_TIMEOUT_SECONDS=120
set BANSA_COMPETITION_MODE=1

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -TimeoutSec 2 http://127.0.0.1:8000/v1/models ^| Out-Null; Write-Host '[OK] Yerel Qwen sunucusu hazir.' -ForegroundColor Green } catch { Write-Host '[UYARI] Qwen sunucusu bulunamadi. Deterministik finansman/kampanya cevaplari yine calisir; RAG/serbest dil icin Qwen'i baslatin.' -ForegroundColor Yellow }"

echo.
echo Streamlit + PostgreSQL launcher baslatiliyor...
echo Parola istenirse yalnizca bu terminale girin.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\run_streamlit_postgresql.ps1"

endlocal
