from bootstrap import P
from pathlib import Path
import json,shutil,time,hashlib
import numpy as np,torch,torchvision,cv2
from resolution_runtime import Detector
from eval_detail import data,coco_metric
from metrics import score_detections
lock=json.loads((P/'results/selection_lock.json').read_text());baseline=lock['baseline_val_AP95'];cv2.setNumThreads(1);trials=[]
@torch.inference_mode()
def evaluate(d,model,split,tag):
 rows=data(split);pred={};gt={}
 for start in range(0,len(rows),4):
  group=rows[start:start+4];ys=d.predict_batch([r[1] for r in group])
  for (n,im,g),y in zip(group,ys):pred[n]={'boxes':y[:,:4],'scores':y[:,4]};gt[n]=g
 out={'model':model,'split':split,'images':len(rows),'device':'cpu','imgsz':d.profile.get('imgsz',640),'coco':coco_metric(pred,gt),'custom':score_detections(pred,gt),'per_image_custom_ap95':{n:score_detections({n:pred[n]},{n:gt[n]})['AP50_95'] for n in gt}}
 (P/'results'/('eval_'+tag+'_'+split+'.json')).write_text(json.dumps(out,indent=2),encoding='utf-8')
 offsets=np.r_[0,np.cumsum([len(pred[n]['boxes']) for n in pred])]
 np.savez_compressed(P/'results'/('pred_'+tag+'_'+split+'.npz'),names=np.array(list(pred)),boxes=np.concatenate([pred[n]['boxes'] for n in pred]),scores=np.concatenate([pred[n]['scores'] for n in pred]),offsets=offsets)
 return out
for size in [576,512]:
 profile={'threads':4,'mode':'LATENCY','fused_channels_last':True,'imgsz':size};d=Detector(P/'models/a2_original.pt',profile=profile);r=evaluate(d,'models/a2_original.pt','val','resolution'+str(size));loss=(baseline-r['coco']['map50_95'])*100
 rows=[f.read_bytes() for f in sorted((P/'data/images/val').glob('*.jpg'))[:30]]
 def call(q):return d(cv2.imdecode(np.frombuffer(q,np.uint8),cv2.IMREAD_COLOR))
 for q in rows[:10]:call(q)
 ts=[]
 for q in rows:
  t=time.perf_counter();call(q);ts.append((time.perf_counter()-t)*1000)
 trial={'imgsz':size,'profile':profile,'validation_AP95_loss_pp':loss,'validation_coco':r['coco'],'p50_ms':float(np.median(ts)),'raw_ms':ts};trials.append(trial);print('CPU_RESOLUTION',size,loss,trial['p50_ms'],flush=True)
eligible=[t for t in trials if t['validation_AP95_loss_pp']<=1]
result={'trials':trials,'rule':'validation AP95 loss <=1pp then minimum CPU single p50; no test labels'}
if eligible:
 best=min(eligible,key=lambda t:t['p50_ms']);alias=P/'models/a2_cpu_resolution.pt';shutil.copy2(P/'models/a2_original.pt',alias);config=dict(best['profile'],label='CPU fused CL '+str(best['imgsz'])+' T4',source_model='models/a2_original.pt');(alias.parent/'cpu_resolution_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8');result['selected']=best
 d=Detector(alias)
 for split in ['val','test']:evaluate(d,alias.relative_to(P).as_posix(),split,alias.stem)
 del d
 import bench_exp3 as bench
 bench.Detector=Detector;bench.run(alias,'LATENCY')
 f=P/'results/bench_a2_cpu_resolution_LATENCY.json';r=json.loads(f.read_text());r['protocol']['input_resolution']=best['imgsz'];r['protocol']['CPU_execution_profile']=config;r['source_sha256']['resolution_runtime.py']=hashlib.sha256((P/'scripts/resolution_runtime.py').read_bytes()).hexdigest();r['source_sha256']['cpu_runtime.py']=hashlib.sha256((P/'scripts/cpu_runtime.py').read_bytes()).hexdigest();r['flops_g']*=best['imgsz']**2/640**2;f.write_text(json.dumps(r,indent=2),encoding='utf-8')
(P/'results/cpu_resolution_trials.json').write_text(json.dumps(result,indent=2),encoding='utf-8');(P/'results/cpu_resolution_done.json').write_text(json.dumps({'completed':True}),encoding='utf-8');print('CPU_RESOLUTION_DONE',flush=True)
