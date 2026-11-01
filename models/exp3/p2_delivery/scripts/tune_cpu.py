from bootstrap import P
from pathlib import Path
import json,time,shutil,gc
import numpy as np,cv2,torch,torchvision
from cpu_runtime import Detector
rows=[f.read_bytes() for f in sorted((P/'data/images/test').glob('*.jpg'))[:32]];cv2.setNumThreads(1)
# Only speed is used for CPU execution tuning; no test labels are read.
if (P/'results/cpu_tuning.json').exists():
 trials=json.loads((P/'results/cpu_tuning.json').read_text())['trials']
else:
 trials=[]
 for model,cl in [('models/a2_original.pt',True),('models/a2_fp32.onnx',False),('models/a2_openvino_fp32/model.xml',False)]:
  for threads in [2,4,8]:
   profile={'threads':threads,'mode':'LATENCY','fused_channels_last':cl};d=Detector(P/model,profile=profile)
   def call(b):return d.predict_batch([cv2.imdecode(np.frombuffer(q,np.uint8),cv2.IMREAD_COLOR) for q in b])
   for _ in range(10):call(rows[:1])
   ts=[]
   for i in range(30):
    t=time.perf_counter();call([rows[i%32]]);ts.append((time.perf_counter()-t)*1000)
   trial={'model':model,'profile':profile,'p50_ms':float(np.median(ts)),'raw_ms':ts};trials.append(trial);print('CPU_TUNE',model,threads,trial['p50_ms'],flush=True);del d;gc.collect()
# Speed-only choice among floating-point runtime settings, then full accuracy verification.
best=min(trials,key=lambda r:r['p50_ms']);f=P/best['model']
if f.suffix=='.xml':
 out=P/'models/a2_cpu_tuned';out.mkdir(exist_ok=True)
 for a in f.parent.glob('model.*'):shutil.copy2(a,out/a.name)
 alias=out/'model.xml'
else:
 alias=P/('models/a2_cpu_tuned'+f.suffix);shutil.copy2(f,alias)
config=dict(best['profile'],source_model=best['model'],label='CPU tuned '+('Torch fused CL' if best['profile']['fused_channels_last'] else 'ORT' if f.suffix=='.onnx' else 'OpenVINO')+' threads'+str(best['profile']['threads']))
(alias.parent/'cpu_tuned_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
(P/'results/cpu_tuning.json').write_text(json.dumps({'criterion':'minimum single-image p50, 10 warmup +30 timed per floating-point profile; no labels','trials':trials,'selected':best,'alias_model':alias.relative_to(P).as_posix(),'config':config},indent=2),encoding='utf-8')
# Reuse the frozen formal harness, overriding only its CPU detector factory.
import bench_exp3 as bench
bench.Detector=Detector
tag=alias.parent.name if alias.suffix=='.xml' else alias.stem
benchfile=P/'results'/('bench_'+tag+'_LATENCY.json')
if not benchfile.exists():bench.run(alias,'LATENCY')
r=json.loads(benchfile.read_text());r['protocol']['CPU_threads']=config['threads'];r['protocol']['CPU_execution_profile']=config;r['source_sha256']['cpu_runtime.py']=__import__('hashlib').sha256((P/'scripts/cpu_runtime.py').read_bytes()).hexdigest()
tag=alias.parent.name if alias.suffix=='.xml' else alias.stem
(P/'results'/('bench_'+tag+'_LATENCY.json')).write_text(json.dumps(r,indent=2),encoding='utf-8')
# Validate full val/test after the speed choice; record actual metric rather than assuming equality.
import eval_detail as ev
ev.Detector=Detector
for split in ['val','test']:ev.evaluate(alias,split)
(P/'results/cpu_tuning_done.json').write_text(json.dumps({'completed':True}),encoding='utf-8');print('CPU_TUNING_DONE',flush=True)
