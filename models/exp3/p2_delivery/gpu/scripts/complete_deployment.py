from bootstrap import P
import subprocess,sys,json,time
assert json.loads((P/'results/md_execution.json').read_text())['status']=='complete'
steps=[
 ['export_student_fp16.py'],['build_student_trt.py'],
 ['bench_exp3.py','--model','models/a2_distilled_trt_fp16.engine','--device','cuda'],
 ['eval_detail.py','--model','models/a2_distilled_trt_fp16.engine'],
 ['eval_detail.py','--model','models/a2_distilled_trt_fp16.engine','--noise','.02'],
 ['native_val.py','--models','models/a2_original.pt,models/a2_distilled.pt,models/m1_teacher.pt','--device','0'],
 ['repeat_gpu.py','--model','models/a2_original.pt'],
 ['repeat_gpu.py','--model','models/a2_trt_fp16.engine'],
 ['repeat_gpu.py','--model','models/a2_distilled_trt_fp16.engine'],
 ['bench_pipeline.py','--model','models/a2_trt_fp16.engine','--device','cuda'],
 ['bench_pipeline.py','--model','models/a2_distilled_trt_fp16.engine','--device','cuda'],
 ['eval_pipeline.py','--model','models/a2_trt_fp16.engine'],
 ['eval_pipeline.py','--model','models/a2_distilled_trt_fp16.engine'],
 ['eval_pipeline.py','--model','models/a2_trt_fp16.engine','--noise','.02'],
 ['eval_pipeline.py','--model','models/a2_distilled_trt_fp16.engine','--noise','.02'],
 ['repeat_pipeline.py','--model','models/a2_trt_fp16.engine'],
 ['repeat_pipeline.py','--model','models/a2_distilled_trt_fp16.engine'],
 ['verify_md.py']]
state={'started':time.strftime('%Y-%m-%d %H:%M:%S'),'steps':[],'status':'running'}
f=P/'results/deployment_execution.json'
if f.exists():state=json.loads(f.read_text(encoding='utf-8'))
state['status']='running'
for i,args in enumerate(steps):
 if any(r['command']==args and r['status']=='complete' for r in state['steps']):continue
 state['current']=args;f.write_text(json.dumps(state,indent=2),encoding='utf-8');print('START',args,flush=True)
 with (P/'results'/('deployment_'+str(i)+'.log')).open('w',encoding='utf-8') as log:
  r=subprocess.run([sys.executable,str(P/'scripts'/args[0]),*args[1:]],cwd=P,stdout=log,stderr=subprocess.STDOUT)
 if r.returncode:
  state['status']='failed';state['returncode']=r.returncode;f.write_text(json.dumps(state,indent=2));raise RuntimeError(args)
 state['steps'].append({'command':args,'status':'complete'})
state['status']='complete';state['current']=None;f.write_text(json.dumps(state,indent=2),encoding='utf-8');print('DEPLOYMENT_DONE',flush=True)
