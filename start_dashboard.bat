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
python start_dashboard.py

pause