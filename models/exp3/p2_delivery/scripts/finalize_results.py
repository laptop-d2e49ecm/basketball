from pathlib import Path
import subprocess,sys
P=Path(__file__).resolve().parents[1]
for name in ['summarize_md.py','plot_temperature.py']:
 subprocess.run([sys.executable,str(P/'scripts'/name)],cwd=P,check=True)
import json,hashlib
checks={name:json.loads((P/name).read_text(encoding='utf-8'))['passed'] for name in ['results/verification_cpu.json','gpu/results/verification_md.json','gpu/results/temperature_verification.json','gpu/results/auto_deployment_verification.json','gpu/results/training_smoke_verification.json','gpu/results/gpu_recommendation.json','results/GPU推理示例_验证.json']}
assert all(checks.values())
proof={'passed':True,'checks':checks,'source_code_sha256':{f.relative_to(P).as_posix():hashlib.sha256(f.read_bytes()).hexdigest() for folder in [P/'scripts',P/'gpu/scripts'] for f in folder.glob('*.py')}}
(P/'results/final_verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
print('ALL_RESULTS_SUMMARIZED_AND_VERIFIED')

subprocess.run([sys.executable,str(P/'scripts/write_acceptance.py')],cwd=P,check=True)
