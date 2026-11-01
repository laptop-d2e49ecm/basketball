"""Run MD experiments sequentially; timings never overlap training."""
from bootstrap import P
import subprocess,sys,json,time,hashlib,traceback
steps=[
 ('train_distillation',['distill_yolo.py','--epochs','12','--microbatch','16'],['results/distill_done.json','models/a2_distilled.pt']),
 ('bench_original_cpu',['bench_exp3.py','--model','models/a2_original.pt','--device','cpu'],['results/bench_a2_original_cpu_LATENCY.json']),
 ('bench_original_gpu',['bench_exp3.py','--model','models/a2_original.pt','--device','cuda'],['results/bench_a2_original_cuda_LATENCY.json']),
 ('bench_trt_gpu',['bench_exp3.py','--model','models/a2_trt_fp16.engine','--device','cuda'],['results/bench_a2_trt_fp16_cuda_LATENCY.json']),
 ('bench_distilled_gpu',['bench_exp3.py','--model','models/a2_distilled.pt','--device','cuda'],['results/bench_a2_distilled_cuda_LATENCY.json']),
 ('eval_original',['eval_detail.py','--model','models/a2_original.pt'],['results/eval_a2_original_test.json']),
 ('eval_original_noise',['eval_detail.py','--model','models/a2_original.pt','--noise','.02'],['results/eval_a2_original_test_noise002.json']),
 ('eval_trt',['eval_detail.py','--model','models/a2_trt_fp16.engine'],['results/eval_a2_trt_fp16_test.json']),
 ('eval_trt_noise',['eval_detail.py','--model','models/a2_trt_fp16.engine','--noise','.02'],['results/eval_a2_trt_fp16_test_noise002.json']),
 ('eval_distilled',['eval_detail.py','--model','models/a2_distilled.pt'],['results/eval_a2_distilled_test.json']),
 ('eval_distilled_noise',['eval_detail.py','--model','models/a2_distilled.pt','--noise','.02'],['results/eval_a2_distilled_test_noise002.json']),
 ('eval_teacher',['eval_detail.py','--model','models/m1_teacher.pt'],['results/eval_m1_teacher_test.json']),
 ('eval_teacher_val',['eval_detail.py','--model','models/m1_teacher.pt','--split','val'],['results/eval_m1_teacher_val.json']),
 ('eval_original_val',['eval_detail.py','--model','models/a2_original.pt','--split','val'],['results/eval_a2_original_val.json'])]
statefile=P/'results/md_execution.json'
state=json.loads(statefile.read_text()) if statefile.exists() else {'started':time.strftime('%Y-%m-%d %H:%M:%S'),'steps':{}}
def save():
 state['updated']=time.strftime('%Y-%m-%d %H:%M:%S');statefile.write_text(json.dumps(state,indent=2),encoding='utf-8')
try:
 for name,args,outputs in steps:
  if state['steps'].get(name,{}).get('status')=='complete' and all((P/f).exists() for f in outputs):continue
  state['current']=name;state['status']='running';state['steps'][name]={'status':'running','start':time.time(),'command':args};save()
  print('START',name,flush=True)
  with (P/'results'/(name+'.log')).open('a',encoding='utf-8') as log:
   r=subprocess.run([sys.executable,str(P/'scripts'/args[0]),*args[1:]],stdout=log,stderr=subprocess.STDOUT,cwd=P)
  if r.returncode:raise RuntimeError(name+' failed with return code '+str(r.returncode))
  assert all((P/f).exists() for f in outputs),outputs
  state['steps'][name].update(status='complete',seconds=time.time()-state['steps'][name]['start'],outputs={f:hashlib.sha256((P/f).read_bytes()).hexdigest() for f in outputs});save();print('DONE',name,flush=True)
 state['status']='complete';state['current']=None;save()
except BaseException as e:
 state['status']='failed';state['error']=str(e);save();raise
