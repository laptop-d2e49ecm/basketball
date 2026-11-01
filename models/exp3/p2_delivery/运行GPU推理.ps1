$ErrorActionPreference = 'Stop'
$taskPy = 'C:\Users\87273\Documents\Codex\2026-10-20\gei\work\yolov8s\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPy)) { $taskPy = 'python' }
$taskImage = (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'data/images/test') -Filter '*.jpg' | Sort-Object Name | Select-Object -First 1).FullName
& $taskPy (Join-Path $PSScriptRoot 'gpu/scripts/infer.py') --model (Join-Path $PSScriptRoot 'gpu/models/a2_distilled_trt_fp16.engine') --image $taskImage --out (Join-Path $PSScriptRoot 'results/GPU推理示例.json') --device cuda --conf .25 --pipeline
