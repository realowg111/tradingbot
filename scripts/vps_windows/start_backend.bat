@echo off
REM ============================================================================
REM Trading Bot - Lanceur rapide pour developpement local sur Windows
REM ============================================================================
REM Utilisable pour tester le backend localement sur Windows avant deploiement
REM sur le VPS.
REM ============================================================================

cd /d "%~dp0\..\..\backend"

if not exist "..\venv\Scripts\python.exe" (
    echo Creation du virtual env...
    python -m venv ..\venv
    ..\venv\Scripts\pip install --upgrade pip
    ..\venv\Scripts\pip install -r requirements.txt
    ..\venv\Scripts\pip install MetaTrader5
)

echo Demarrage du backend sur http://localhost:8001
..\venv\Scripts\python -m uvicorn server:app --host 0.0.0.0 --port 8001 --reload

pause
