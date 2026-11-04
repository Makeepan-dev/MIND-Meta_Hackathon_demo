@echo off
title MIND — Mageepan's Intelligence Network Device (Meta Hackathon Edition)
cd /d "%~dp0"

echo ============================================================
echo   MIND — Mageepan's Intelligence Network Device
echo   Meta Global AI Developer Hackathon Edition
echo ============================================================

if exist ".venv\Scripts\python.exe" (
    echo [MIND] Using virtual environment: .venv
    ".venv\Scripts\python.exe" run_hackathon_app.py %*
    goto :eof
)

if exist "venv\Scripts\python.exe" (
    echo [MIND] Using virtual environment: venv
    "venv\Scripts\python.exe" run_hackathon_app.py %*
    goto :eof
)

echo [MIND] Launching with system Python...
python run_hackathon_app.py %*
