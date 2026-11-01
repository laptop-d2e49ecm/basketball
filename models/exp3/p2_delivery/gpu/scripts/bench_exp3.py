from bootstrap import P,STAGE1,SOURCE_ROOT
import argparse,json,time,platform,sys,gc
from pathlib import Path
import numpy as np,cv2,torch,torchvision,psutil
from infer import Detector,make_graph_backend,shared_nms
WARMUP,N_SINGLE,N_BATCH,BS=10,100,20,32

class Encoded:
 def __init__(self,path,device=None,ov_mode='LATENCY',graph=False):
  self.graph=graph
  if graph:
   sys.path.insert(0,str(STAGE1/'code'))
   import experiment
   experiment.P=STAGE1;experiment.setup();self.e=experiment;self.b=make_graph_backend(path);self.device='cuda'
  else:self.det=Detector(path,device=device,ov_mode=ov_mode);self.device=self.det.device
 def __call__(self,rows):
  if self.graph:
   def decode(row):
    im=cv2.imdecode(np.frombuffer(row['jpeg'],np.uint8),cv2.IMREAD_COLOR);return Detector.letterbox_u8(im)
   prepared=list(self.b.pool.map(decode,rows)) if len(rows)>1 else [decode(rows[0])]
   x=self.b.prepare(np.stack([q[0] for q in prepared]));ys=shared_nms(self.b.forward(x));out=[y.float().cpu().numpy() for y in ys]
   for a,(_,meta) in zip(out,prepared):
    r,dx,dy,w,h=meta;a[:,[0,2]]=(a[:,[0,2]]-dx)/r;a[:,[1,3]]=(a[:,[1,3]]-dy)/r;a[:,[0,2]]=a[:,[0,2]].clip(0,w);a[:,[1,3]]=a[:,[1,3]].clip(0,h)
   return out
  imgs=[cv2.imdecode(np.frombuffer(r['jpeg'],np.uint8),cv2.IMREAD_COLOR) for r in rows];return self.det.predict_batch(imgs)
 def sync(self):
  if self.device=='cuda':torch.cuda.synchronize()

def run(path,device=None,ov_mode='LATENCY',graph=False,stability=1000):
 torch.set_num_threads(4);cv2.setNumThreads(1);torch.backends.cudnn.benchmark=False;torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
 rows=[{'jpeg':f.read_bytes()} for f in sorted((P.parent/'data/images/test').glob('*.jpg'))[:32]]
 model=Path(path);tag=('graph_'+model.stem if graph else model.parent.name if model.suffix=='.xml' else model.stem)+'_'+(device or 'auto')+'_'+ov_mode
 b=Encoded(path,device,ov_mode,graph);proc=psutil.Process();rss=[];raw={};torch.cuda.empty_cache()
 if b.device=='cuda':torch.cuda.reset_peak_memory_stats()
 with torch.inference_mode():
  for batch,count in [(1,N_SINGLE),(BS,N_BATCH)]:
   try:
    for _ in range(WARMUP):b(rows[:batch])
    b.sync();ts=[]
    for i in range(count):
     group=[rows[(i*batch+j)%len(rows)] for j in range(batch)];b.sync();t=time.perf_counter();out=b(group);b.sync();ts.append((time.perf_counter()-t)*1000)
     if i%10==0:rss.append(proc.memory_info().rss)
    raw[str(batch)]={'raw_ms':ts,'p50':float(np.percentile(ts,50)),'p95':float(np.percentile(ts,95)),'mean':float(np.mean(ts))}
   except torch.cuda.OutOfMemoryError as ex:
    raw[str(batch)]={'raw_ms':[],'p50':None,'p95':None,'mean':None,'failed':'CUDA OOM at requested batch'+str(batch)};torch.cuda.empty_cache()
  stability_rss=[]
  for i in range(stability):
   b([rows[i%32]])
   if (i+1)%100==0:b.sync();stability_rss.append({'iteration':i+1,'RSS_bytes':proc.memory_info().rss})
  vals=[v['RSS_bytes'] for v in stability_rss];variation=(max(vals)-min(vals))/float(np.mean(vals)) if vals else None
 backend='pytorch' if model.suffix=='.pt' or graph else 'onnxruntime-cpu' if model.suffix=='.onnx' else 'openvino-cpu' if model.suffix=='.xml' else 'tensorrt-local-rtx3050'
 if model.suffix=='.xml':size=sum(f.stat().st_size for f in model.parent.glob('model.*'))
 else:size=model.stat().st_size
 result={'model':str(model.relative_to(P)) if model.is_relative_to(P) else str(model),'backend':backend,'precision':'int8' if 'int8' in str(model) else 'fp16' if 'fp16' in str(model) or graph else 'fp32','hardware':torch.cuda.get_device_name() if b.device=='cuda' else json.loads((P/'results/environment.json').read_text())['CPU'],'size_mb':size/1e6,'params_m':25.856899 if 'teacher' in model.stem else 3.138003,'flops_g':None if 'teacher' in model.stem else 8.6378112,'lat_single_ms_p50':raw['1']['p50'],'lat_single_ms_p95':raw['1']['p95'],'lat_batch32_ms':raw['32']['mean'],'fps':BS*1000/raw['32']['mean'] if raw['32']['mean'] else None,'map50':None,'map50_95':None,'ap_small':None,'ap_medium':None,'ap_large':None,'noise_map50':None,'mem_peak_mb':max(rss+vals)/1e6,'torch_cuda_peak_allocated_mb':torch.cuda.max_memory_allocated()/1e6 if b.device=='cuda' else None,'trt_native_cuda_memory_included':False,'ov_mode':ov_mode if model.suffix=='.xml' else None,'raw':raw,'stability':{'iterations':stability,'samples':stability_rss,'range_over_mean':variation,'within_5pct':variation<=.05 if variation is not None else None},'protocol':{'warmup':WARMUP,'single':N_SINGLE,'batch_repeats':N_BATCH,'batch_size':BS,'CPU_threads':4,'scope':'in-memory JPEG decode -> letterbox RGB normalization -> transfer -> model -> shared torchvision NMS -> CPU arrays; no disk I/O/load/cold-start/Web/video','timing':'synchronized CUDA wall time','area_metrics':'COCOeval; absent area=-1 converted to null','VRAM_caveat':'torch allocator peak excludes engine native buffers'},'environment':{'python':platform.python_version(),'torch':torch.__version__,'device':b.device}}
 (P/'results'/('bench_'+tag+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8');print('BENCH_DONE',tag,result['lat_single_ms_p50'],result['fps'],result['stability']['within_5pct'],flush=True)
 return result
if __name__=='__main__':
 q=argparse.ArgumentParser();q.add_argument('--model',required=True);q.add_argument('--device');q.add_argument('--ov-mode',default='LATENCY');q.add_argument('--graph',action='store_true');q.add_argument('--stability',type=int,default=1000);a=q.parse_args();run(P/a.model,a.device,a.ov_mode,a.graph,a.stability)
