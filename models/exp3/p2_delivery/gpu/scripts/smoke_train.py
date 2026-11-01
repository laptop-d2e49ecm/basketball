from bootstrap import P
import subprocess,sys,json
rows=[]
for dtype in ['auto','float16']:
 r=subprocess.run([sys.executable,str(P/'scripts/distill_yolo.py'),'--fresh','--smoke','--epochs','12','--amp-dtype',dtype],cwd=P,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8')
 (P/'results'/('training_smoke_'+dtype+'.log')).write_text(r.stdout,encoding='utf-8')
 assert r.returncode==0 and 'STUDENT_GRAD_OK' in r.stdout and 'SMOKE_OK' in r.stdout and 'optimizer stepped' in r.stdout,r.stdout[-3000:]
 rows.append({'amp':dtype,'gradient_flow':True,'optimizer_update':True})
(P/'results/training_smoke_verification.json').write_text(json.dumps({'passed':True,'checks':rows},indent=2),encoding='utf-8');print('TRAINING_SMOKE_VERIFIED')
