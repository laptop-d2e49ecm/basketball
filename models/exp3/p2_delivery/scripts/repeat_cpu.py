from bootstrap import P
from resolution_runtime import Detector
import argparse,time,json,cv2,numpy as np,torch
q=argparse.ArgumentParser();q.add_argument('--model',required=True);q.add_argument('--ov-mode',default='LATENCY');q.add_argument('--out',required=True);a=q.parse_args();torch.set_num_threads(4);cv2.setNumThreads(1)
d=Detector(P/a.model,ov_mode=a.ov_mode);rows=[p.read_bytes() for p in sorted((P/'data/images/test').glob('*.jpg'))[:32]];result={'model':a.model,'device':'cpu','ov_mode':a.ov_mode,'repeat':'independent process second run'}
def call(group):return d.predict_batch([cv2.imdecode(np.frombuffer(b,np.uint8),cv2.IMREAD_COLOR) for b in group])
for batch,count in [(1,100),(32,20)]:
 for _ in range(10):call(rows[:batch])
 ts=[]
 for i in range(count):
  group=[rows[(i*batch+j)%32] for j in range(batch)];t=time.perf_counter();call(group);ts.append((time.perf_counter()-t)*1000)
 result[str(batch)]={'raw_ms':ts,'p50':float(np.median(ts)),'p95':float(np.percentile(ts,95)),'mean':float(np.mean(ts))}
(P/a.out).write_text(json.dumps(result,indent=2),encoding='utf-8');print('CPU_REPEAT_DONE',a.model,result['1']['p50'],flush=True)
