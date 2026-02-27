@echo off
echo Stoppe Dashboard...

powershell -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*start_dashboard*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo Dashboard gestoppt.
timeout /t 2 >nul
