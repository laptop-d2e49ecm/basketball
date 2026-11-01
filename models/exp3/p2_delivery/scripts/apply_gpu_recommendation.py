from pathlib import Path
import json,hashlib,subprocess,sys
import numpy as np
P=Path(__file__).resolve().parents[1];G=P/'gpu'
f=G/'results/gpu_recommendation.json';r=json.loads(f.read_text(encoding='utf-8'));s=r['selected'];assert r['post_lock_test_completed']
base=json.loads((G/'results/eval_a2_original_test.json').read_text())['coco'];diff=max(abs(r['post_lock_test'][k]-base[k]) for k in ['map50','map50_95'])*100
assert diff<=1
model=G/s['model'];assert hashlib.sha256(model.read_bytes()).hexdigest()==r['model_sha256']
r['post_lock_test_maximum_AP_difference_pp']=diff;r['passed']=True;f.write_text(json.dumps(r,indent=2),encoding='utf-8')
image=sorted((P/'data/images/test').glob('*.jpg'))[0];out=P/'results/GPU推理示例.json'
args=[sys.executable,str(G/'scripts/infer.py'),'--model',str(model),'--image',str(image),'--out',str(out),'--device','cuda','--conf','.25']+(['--pipeline'] if s['pipeline'] else [])
subprocess.run(args,check=True);a=np.asarray(json.loads(out.read_text()),dtype=np.float32).reshape(-1,6);assert np.isfinite(a).all() and (a[:,4]>=.25).all()
proof={'passed':True,'model':model.relative_to(P).as_posix(),'model_sha256':r['model_sha256'],'image':image.relative_to(P).as_posix(),'detections':len(a),'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'pipeline':s['pipeline']}
(P/'results/GPU推理示例_验证.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
lines=["$ErrorActionPreference = 'Stop'",r"$taskPy = 'C:\Users\87273\Documents\Codex\2026-10-20\gei\work\yolov8s\.venv\Scripts\python.exe'","if (-not (Test-Path -LiteralPath $taskPy)) { $taskPy = 'python' }","$taskImage = (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'data/images/test') -Filter '*.jpg' | Sort-Object Name | Select-Object -First 1).FullName","& $taskPy (Join-Path $PSScriptRoot 'gpu/scripts/infer.py') --model (Join-Path $PSScriptRoot 'gpu/"+s['model']+"') --image $taskImage --out (Join-Path $PSScriptRoot 'results/GPU推理示例.json') --device cuda --conf .25"+(' --pipeline' if s['pipeline'] else '')]
(P/'运行GPU推理.ps1').write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
t=(P/'README_MD_TEMPLATE.md').read_text(encoding='utf-8');t=t.replace('--model gpu/models/a2_trt_fp16.engine --image','--model gpu/'+s['model']+' --image',1)
t+='\n默认GPU部署：'+s['model']+'，在本机已测候选中按验证精度门槛与单张p50选出；选择记录在gpu/results/gpu_selection_lock.json，锁定后最终测试在gpu/results/gpu_recommendation.json。运行GPU推理.ps1与报告推荐使用同一模型。\n'
(P/'README_MD_TEMPLATE.md').write_text(t,encoding='utf-8');print('RECOMMENDATION_APPLIED',s['model'],flush=True)
