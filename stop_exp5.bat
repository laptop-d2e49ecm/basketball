@echo off
chcp 936 >nul
setlocal EnableExtensions
title CourtVision 实验5 停止器

echo 正在停止实验5 相关进程 ...

for %%P in (8000 5173) do (
  for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":%%P" ^| findstr LISTENING') do (
    echo   结束端口 %%P 的进程 PID %%i
    taskkill /PID %%i /F >nul 2>&1
  )
)

echo   结束视频 Worker 进程 ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*worker.main*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo 完成。若窗口仍在，可直接关闭其控制台窗口。
ping -n 3 127.0.0.1 >nul
endlocal
