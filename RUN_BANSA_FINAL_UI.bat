@echo off
setlocal
cd /d "%~dp0"

echo ================================================================
echo BANSA V22 - LIVE DEMO FINAL
echo ================================================================
echo.

set BANSA_COMPETITION_MODE=1
set BANSA_LOCAL_AGENT_ENABLED=1
set BANSA_LOCAL_LLM_BASE_URL=http://127.0.0.1:8000/v1
set BANSA_LOCAL_LLM_MODEL=bansa-qwen-local
set BANSA_FAST_NATURALIZER_TIMEOUT_SECONDS=0.8
set BANSA_PREWARM_RAG_ON_STARTUP=0

python -m streamlit run Ana_Sayfa.py

endlocal
