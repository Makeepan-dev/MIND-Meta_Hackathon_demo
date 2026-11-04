@echo off
title MIND — Meta Global AI Hackathon Desktop Console
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%~dp0MIND_GameDev;%~dp0MIND_Code;%~dp0
echo ============================================================
echo   Starting MIND — Meta Global AI Hackathon Edition...
echo   JARVIS-Inspired Animated Circular AI Core Online
echo ============================================================
"%~dp0venv\Scripts\python.exe" "%~dp0run_hackathon_app.py"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with code %ERRORLEVEL%.
    pause
)
