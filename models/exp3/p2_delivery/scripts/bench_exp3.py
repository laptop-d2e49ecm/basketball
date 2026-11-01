"""CPU-only formal benchmark, memory JPEG -> CPU detection boxes."""
from bootstrap import P
import argparse,json,time,platform,hashlib
from pathlib import Path
import numpy as np,cv2,torch,torchvision,psutil
from infer import Detector
WARMUP,N_SINGLE,N_BATCH,BS=10,100,20,32

def run(path,ov_mode='LATENCY'):
 torch.set_num_threads(4);cv2.setNumThreads(1)
 rows=[f.read_bytes() for f in sorted((P/'data/images/test').glob('*.jpg'))[:32]]
 det=Detector(path,ov_mode=ov_mode);proc=psutil.Process();rss=[];raw={}
 def call(jpegs):return det.predict_batch([cv2.imdecode(np.frombuffer(b,np.uint8),cv2.IMREAD_COLOR) for b in jpegs])
 with torch.inference_mode():
  for batch,count in [(1,N_SINGLE),(BS,N_BATCH)]:
   for _ in range(WARMUP):call(rows[:batch])
   ts=[]
   for i in range(count):
    group=[rows[(i*batch+j)%len(rows)] for j in range(batch)];start=time.perf_counter();call(group);ts.append((time.perf_counter()-start)*1000)
    if i%10==0:rss.append(proc.memory_info().rss)
   raw[str(batch)]={'raw_ms':ts,'p50':float(np.percentile(ts,50)),'p95':float(np.percentile(ts,95)),'mean':float(np.mean(ts))}
   print('TIMED',Path(path).name,ov_mode,batch,raw[str(batch)]['p50'],flush=True)
  samples=[]
  for i in range(1000):
   call([rows[i%32]])
   if (i+1)%100==0:samples.append({'iteration':i+1,'RSS_bytes':proc.memory_info().rss});print('STABILITY',i+1,flush=True)
 vals=[v['RSS_bytes'] for v in samples];variation=(max(vals)-min(vals))/float(np.mean(vals));model=Path(path);tag=(model.parent.name if model.suffix=='.xml' else model.stem)+'_'+ov_mode
 size=sum(f.stat().st_size for f in model.parent.glob('model.*')) if model.suffix=='.xml' else model.stat().st_size
 result={'model':model.relative_to(P).as_posix(),'backend':'pytorch-cpu' if model.suffix=='.pt' else 'onnxruntime-cpu' if model.suffix=='.onnx' else 'openvino-cpu','device':'cpu','ov_mode':ov_mode if model.suffix=='.xml' else None,'size_mb':size/1e6,'params_m':3.138003,'flops_g':8.6378112,'lat_single_ms_p50':raw['1']['p50'],'lat_single_ms_p95':raw['1']['p95'],'lat_batch32_ms':raw['32']['mean'],'fps':32000/raw['32']['mean'],'mem_peak_mb':max(rss+vals)/1e6,'raw':raw,'stability':{'iterations':1000,'samples':samples,'range_over_mean':variation,'within_5pct':variation<=.05},'protocol':{'warmup':10,'single':100,'batch_size':32,'batch_repeats':20,'CPU_threads':4,'scope':'in-memory JPEG decode -> letterbox RGB float32 -> CPU backend -> shared torchvision NMS -> original-coordinate arrays','exclusions':'disk I/O, model load, cold-start, Web/video'},'source_sha256':{n:hashlib.sha256((P/'scripts'/n).read_bytes()).hexdigest() for n in ['infer.py','bench_exp3.py','bootstrap.py']},'date':time.strftime('%Y-%m-%d %H:%M:%S')}
 (P/'results'/('bench_'+tag+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8');print('BENCH_DONE',tag,result['lat_single_ms_p50'],result['fps'],flush=True)
if __name__=='__main__':
 q=argparse.ArgumentParser();q.add_argument('--model',required=True);q.add_argument('--ov-mode',default='LATENCY');a=q.parse_args();run(P/a.model,a.ov_mode)
