from bootstrap import P
import json,subprocess,sys,hashlib,time,shutil
from runtime_lock import acquire
lock=acquire()
def load(f):return json.loads(f.read_text(encoding='utf-8'))
for stem in ['a2_trt_fp16','a2_distilled_trt_fp16']:
 f=P/'results'/('eval_'+stem+'_pipeline_val.json')
 if not f.exists():
  with (P/'results'/('recommend_val_'+stem+'.log')).open('w',encoding='utf-8') as log:subprocess.run([sys.executable,str(P/'scripts/eval_pipeline.py'),'--model','models/'+stem+'.engine','--split','val'],cwd=P,stdout=log,stderr=subprocess.STDOUT,check=True)
base=load(P/'results/eval_a2_original_val.json')['coco'];rows=[]
for stem,pipeline in [('a2_original',False),('a2_distilled',False),('a2_temperature',False),('a2_trt_fp16',True),('a2_distilled_trt_fp16',True)]:
 tag=stem+('_pipeline' if pipeline else '');v=load(P/'results'/('eval_'+tag+'_val.json'))['coco'];b=load(P/'results'/('bench_'+tag+'_cuda_LATENCY.json'))
 diff=max(abs(v[k]-base[k]) for k in ['map50','map50_95'])*100
 rows.append({'model':b['model'].replace('\\','/'),'tag':tag,'pipeline':pipeline,'val':v,'maximum_val_AP_difference_pp':diff,'eligible':diff<=1,'p50_ms':b['lat_single_ms_p50'],'batch32_fps':b['fps']})
eligible=[r for r in rows if r['eligible']];winner=min(eligible,key=lambda r:r['p50_ms'])
proof={'criterion':'validation AP50/AP50:95 maximum absolute difference <=1 percentage point; among eligible GPU candidates choose lowest formal single-image p50; test labels not used','candidates':rows,'selected':winner,'model_sha256':hashlib.sha256((P/winner['model']).read_bytes()).hexdigest(),'date':time.strftime('%Y-%m-%d %H:%M:%S')}
(P/'results/gpu_selection_lock.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
script='eval_pipeline.py' if winner['pipeline'] else 'eval_detail.py';f=P/'results'/('eval_'+winner['tag']+'_test.json')
if f.exists():shutil.copy2(f,P/'results'/('before_selection_'+f.name))
with (P/'results/final_selected_test.log').open('w',encoding='utf-8') as log:subprocess.run([sys.executable,str(P/'scripts'/script),'--model',winner['model']],cwd=P,stdout=log,stderr=subprocess.STDOUT,check=True)
proof['post_lock_test']=load(f)['coco'];proof['post_lock_test_completed']=True
(P/'results/gpu_recommendation.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print('GPU_RECOMMENDED',winner['model'],winner['p50_ms'],flush=True)
