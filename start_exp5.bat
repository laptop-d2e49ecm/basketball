@echo off
chcp 936 >nul
setlocal EnableExtensions
title CourtVision 实验5 启动器

set "ROOT=%~dp0"
set "BE=%ROOT%exp4\complete_web_system\backend"
set "FE=%ROOT%exp4\complete_web_system\frontend"
set "PY=%BE%\.venv\Scripts\python.exe"
set "LAUNCH=%ROOT%scripts\run\launch.py"
set "VITEJS=%ROOT%scripts\run\run_vite.mjs"
set "LOGS=%ROOT%logs"

echo ============================================================
echo  CourtVision  AI 篮球赛事解说  实验5 一键启动
echo ============================================================
echo  后端：http://127.0.0.1:8000   （FastAPI + ONNX Runtime）
echo  前端：http://127.0.0.1:5173   （Vue 3 + Vite）
echo  Agent：http://127.0.0.1:5173/agent
echo ------------------------------------------------------------

if not exist "%LOGS%" mkdir "%LOGS%"

if not exist "%PY%" (
  echo [错误] 找不到后端虚拟环境：
  echo        %PY%
  echo        请先按 README 创建 venv 并安装依赖。
  pause & exit /b 1
)
if not exist "%FE%\node_modules" (
  echo [错误] 前端依赖未安装：%FE%\node_modules
  echo        请在 frontend 目录执行 pnpm install（或 npm install）。
  pause & exit /b 1
)

set "NODE_EXE=C:\sofeware\AI Api\dsh workspace\fish\tools\node\node-v22.12.0-win-x64\node.exe"
if not exist "%NODE_EXE%" (
  for %%i in (node.exe) do set "NODE_EXE=%%~$PATH:i"
)
if not exist "%NODE_EXE%" (
  echo [错误] 找不到 Node.js。请安装 Node 18+ 或把 node.exe 放到 PATH。
  pause & exit /b 1
)

echo [1/4] 检查端口占用 ...
"%PY%" "%LAUNCH%" port 8000
if errorlevel 1 (
  echo        8000 已被占用：先运行 stop_exp5.bat 再启动。
  pause & exit /b 1
)
"%PY%" "%LAUNCH%" port 5173
if errorlevel 1 (
  echo        5173 已被占用：先运行 stop_exp5.bat 再启动。
  pause & exit /b 1
)

echo [2/4] 启动后端（独立窗口，最小化）...
start "exp5-backend" /min /d "%BE%" "%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"%PY%" "%LAUNCH%" wait http://127.0.0.1:8000/api/v1/health 120
if errorlevel 1 (
  echo        后端 120 秒内未就绪，请查看弹出的后端窗口报错。
  pause & exit /b 1
)

echo [3/4] 启动前端（独立窗口，最小化）...
start "exp5-frontend" /min /d "%ROOT%scripts\run" cmd /c ""%NODE_EXE%" "%VITEJS%" --host 127.0.0.1 --port 5173 --strictPort"
"%PY%" "%LAUNCH%" wait http://127.0.0.1:5173/ 90
if errorlevel 1 (
  echo        前端 90 秒内未就绪，请查看弹出的前端窗口报错。
  pause & exit /b 1
)

echo [4/4] 模型自检 ...
"%PY%" "%LAUNCH%" health

echo.
echo ------------------------------------------------------------
echo  启动完成。浏览器将打开 /agent 页面。
echo  关闭服务：双击 stop_exp5.bat
echo ------------------------------------------------------------
start "" http://127.0.0.1:5173/agent
ping -n 4 127.0.0.1 >nul
endlocal
