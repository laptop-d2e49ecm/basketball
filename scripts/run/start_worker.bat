@echo off
chcp 936 >nul
rem 由 start_exp5.bat 调起：在 backend 目录下运行视频 Worker，输出写入 logs\worker.log
cd /d "%~dp0..\..\exp4\complete_web_system\backend"
"%~dp0..\..\exp4\complete_web_system\backend\.venv\Scripts\python.exe" -m worker.main 1> "%~dp0..\..\logs\worker.log" 2>&1
