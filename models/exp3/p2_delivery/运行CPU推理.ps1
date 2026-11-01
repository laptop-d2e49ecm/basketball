$ErrorActionPreference = 'Stop'
$taskPy = 'C:\Users\87273\Documents\Codex\2026-10-20\gei\work\yolov8s\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPy)) { $taskPy = 'python' }
$taskImage = (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'data/images/test') -Filter '*.jpg' | Sort-Object Name | Select-Object -First 1).FullName
& $taskPy (Join-Path $PSScriptRoot 'scripts/run_cpu.py') --model (Join-Path $PSScriptRoot 'models/a2_cpu_tuned/model.xml') --image $taskImage --out (Join-Path $PSScriptRoot 'results/CPU推理示例.json') --conf .25 --ov-mode LATENCY
