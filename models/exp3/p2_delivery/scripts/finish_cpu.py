from bootstrap import P
import json,subprocess,sys,time
lock=json.loads((P/'results/selection_lock.json').read_text())
models=[('models/a2_original.pt','LATENCY'),('models/a2_fp32.onnx','LATENCY'),('models/a2_fp16.onnx','LATENCY'),(lock['selected_int8'],'LATENCY'),('models/a2_openvino_fp32/model.xml','LATENCY'),('models/a2_openvino_fp32/model.xml','THROUGHPUT'),(lock['selected_openvino_int8'],'LATENCY'),(lock['selected_openvino_int8'],'THROUGHPUT')]
for model,mode in models:
 f=P/model;key=f.parent.name if f.suffix=='.xml' else f.stem
 for split in ['test']:
  out=P/'results'/('eval_'+key+'_'+split+'.json')
  if not out.exists():subprocess.run([sys.executable,str(P/'scripts/eval_detail.py'),'--model',model],check=True)
 out=P/'results'/('bench_'+key+'_'+mode+'.json')
 if out.exists():continue
 print('CPU_BENCH',model,mode,flush=True)
 subprocess.run([sys.executable,str(P/'scripts/bench_exp3.py'),'--model',model,'--ov-mode',mode],check=True)
subprocess.run([sys.executable,str(P/'scripts/verify_cpu.py')],check=True)
(P/'results/cpu_done.json').write_text(json.dumps({'completed':True,'configs':len(models),'date':time.strftime('%Y-%m-%d %H:%M:%S')}),encoding='utf-8')
print('CPU_EXPERIMENTS_DONE',flush=True)
