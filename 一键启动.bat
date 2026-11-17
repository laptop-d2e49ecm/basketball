@echo off
setlocal
title Basketball AI - Launcher
cd /d "%~dp0"
set "ROOT=%~dp0exp4\complete_web_system"
set "BACKEND=%ROOT%\backend"
set "VENV=%~dp0.venv\Scripts\python.exe"
if not exist "%BACKEND%\logs" md "%BACKEND%\logs"

echo ================================================
echo   Basketball AI commentary system - one-click start
echo ================================================
echo.

echo [1/3] Backend API  (127.0.0.1:8000)
netstat -ano | findstr /c:":8000 " | findstr /c:"LISTENING" >nul 2>&1
if errorlevel 1 (
    echo       starting...
    start "basketball-api" /min cmd /c "cd /d %BACKEND% && %VENV% -m uvicorn app.main:app --port 8000 > logs\api_auto.log 2>&1"
) else (
    echo       already running, skip.
)

echo [2/3] Analysis worker
powershell -NoProfile -Command "if ((Get-CimInstance Win32_Process -Filter \"Name='python.exe' AND CommandLine LIKE '%%worker.main%%'\").Count -gt 0) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo       starting...
    start "basketball-worker" /min cmd /c "cd /d %BACKEND% && %VENV% -m worker.main > logs\worker_auto.log 2>&1"
) else (
    echo       already running, skip.
)

echo [3/3] Frontend  (127.0.0.1:5173)
netstat -ano | findstr /c:":5173 " | findstr /c:"LISTENING" >nul 2>&1
if errorlevel 1 (
    echo       starting...
    where pnpm >nul 2>&1
    if errorlevel 1 (
        start "basketball-web" /min cmd /c "cd /d %ROOT%\frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort > ..\backend\logs\vite_auto.log 2>&1"
    ) else (
        start "basketball-web" /min cmd /c "cd /d %ROOT%\frontend && pnpm dev --host 127.0.0.1 --port 5173 --strictPort > ..\backend\logs\vite_auto.log 2>&1"
    )
) else (
    echo       already running, skip.
)

echo.
echo Waiting for services to be ready...
set /a TRIES=0
:waitloop
set /a TRIES+=1
if %TRIES% GEQ 60 goto open
netstat -ano | findstr /c:":8000 " | findstr /c:"LISTENING" >nul 2>&1
if errorlevel 1 (%SystemRoot%\System32\timeout.exe /t 1 /nobreak >nul & goto waitloop)
netstat -ano | findstr /c:":5173 " | findstr /c:"LISTENING" >nul 2>&1
if errorlevel 1 (%SystemRoot%\System32\timeout.exe /t 1 /nobreak >nul & goto waitloop)

:open
echo Opening workbench page in browser...
start "" "http://127.0.0.1:5173/courtvision.html"
echo.
echo All set. You can close this window.
%SystemRoot%\System32\timeout.exe /t 6 >nul
