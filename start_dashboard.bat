@echo off
echo =====================================
echo    MEBIS STATISTIK DASHBOARD
echo =====================================
echo.

REM Prüfe ob Python verfügbar ist
python --version >nul 2>&1
if errorlevel 1 (
    echo Fehler: Python ist nicht installiert oder nicht im PATH!
    echo Bitte installieren Sie Python 3.8 oder höher.
    pause
    exit /b 1
)

REM Starte das Dashboard
echo Starte Dashboard...
REM Prüfe ob .venv existiert und aktiviere es
if exist ".venv\Scripts\activate.bat" (
    echo Aktiviere virtuelle Umgebung (.venv)...
    call .venv\Scripts\activate.bat
    echo Virtuelle Umgebung aktiviert.
    echo.
) else (
    echo Keine virtuelle Umgebung gefunden - verwende System-Python.
    echo.
)
python start_dashboard.py

pause