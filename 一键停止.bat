@echo off
setlocal
title Basketball AI - Stop
echo Stopping basketball AI services...

echo [1/3] Frontend (port 5173)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /c:":5173 " ^| findstr /c:"LISTENING"') do taskkill /PID %%p /T /F >nul 2>&1

echo [2/3] Backend API (port 8000)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /c:":8000 " ^| findstr /c:"LISTENING"') do taskkill /PID %%p /T /F >nul 2>&1

echo [3/3] Analysis worker
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' AND CommandLine LIKE '%%worker.main%%'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo.
echo Done. All basketball services stopped.
%SystemRoot%\System32\timeout.exe /t 4 >nul
