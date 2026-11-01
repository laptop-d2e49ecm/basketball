from pathlib import Path
import time,subprocess
P=Path(__file__).resolve().parents[1]
while not (P/'results/cpu_done.json').exists():time.sleep(5)
yolo=Path(r'C:/Users/87273/Documents/Codex/2026-10-20/gei/work/yolov8s/.venv/Scripts/python.exe');report=Path(r'C:/Users/87273/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
for py,script in [(yolo,'plot_cpu.py'),(report,'build_cpu_report.py'),(report,'render_cpu_report.py')]:
 print('CPU_ARTIFACT_STAGE',script,flush=True);subprocess.run([str(py),str(P/'scripts'/script)],check=True)
print('CPU_REPORT_READY_FOR_VISUAL_REVIEW',flush=True)
