from bootstrap import P
from pathlib import Path
import json,hashlib,py_compile,zipfile,subprocess,sys
import numpy as np,cv2,torch,torchvision
from resolution_runtime import Detector
from analyze_cpu import main,load
if not (P/'results/cpu_tuning_done.json').exists():subprocess.run([sys.executable,str(P/'scripts/tune_cpu.py')],check=True)
if not (P/'results/cpu_resolution_done.json').exists():subprocess.run([sys.executable,str(P/'scripts/try_resolution_cpu.py')],check=True)
main()
for f in (P/'scripts').glob('*.py'):py_compile.compile(str(f),doraise=True)
source=P.parents[2]/'模型设计与训练.zip'
sha_source=None
if source.exists():
 with zipfile.ZipFile(source) as z:sha_source=hashlib.sha256(z.read('A2_yolov8n/weights/best.pt')).hexdigest()
sha_local=hashlib.sha256((P/'models/a2_original.pt').read_bytes()).hexdigest()
assert sha_local=='2e8624bf93eba97a0adc7f899fbb8e4cd9fd90e42f6546c74f32cc9ba9134776'
if sha_source is not None:assert sha_source==sha_local
rec=load(P/'results/cpu_recommendation.json');d=Detector(P/rec['model'],ov_mode=rec['ov_mode'] or 'LATENCY')
f=sorted((P/'data/images/test').glob('*.jpg'))[0];im=cv2.imdecode(np.frombuffer(f.read_bytes(),np.uint8),cv2.IMREAD_COLOR);checks=[]
for w,h in [(640,640),(960,360),(320,800)]:
 y=d(cv2.resize(im,(w,h)));assert np.isfinite(y).all();assert ((y[:,[0,2]]>=0)&(y[:,[0,2]]<=w)).all();assert ((y[:,[1,3]]>=0)&(y[:,[1,3]]<=h)).all();checks.append({'width':w,'height':h,'detections':len(y)})
shapes=[]
for n in [1,4,32]:
 y=d.raw(np.repeat(d.letterbox(im)[0][None],n,axis=0));size=d.profile.get('imgsz',640);assert tuple(y.shape)==(n,5,sum((size//stride)**2 for stride in [8,16,32]));shapes.append(list(y.shape))
# Verify reused CPU accuracy archives against the final CPU-only interface.
consistency=[]
for model in ['models/a2_fp32.onnx',load(P/'results/selection_lock.json')['selected_int8'],'models/a2_openvino_fp32/model.xml',load(P/'results/selection_lock.json')['selected_openvino_int8']]:
 obj=Detector(P/model);k=Path(model).parent.name if model.endswith('.xml') else Path(model).stem;a=np.load(P/'results'/('pred_'+k+'_test.npz'))
 group=sorted((P/'data/images/test').glob('*.jpg'))[:4];x=np.stack([obj.letterbox(cv2.imdecode(np.frombuffer(p.read_bytes(),np.uint8),cv2.IMREAD_COLOR))[0] for p in group]);outs=obj.tensor_batch(x)
 for p,y in zip(group,outs):
  ix=list(a['names']).index(p.name);lo,hi=a['offsets'][ix:ix+2];stored=np.column_stack([a['boxes'][lo:hi],a['scores'][lo:hi]])
  yy=y[:,:5].copy();yy[:,:4]=yy[:,:4].clip(0,640);assert yy.shape==stored.shape;diff=float(np.max(np.abs(yy-stored))) if len(y) else 0.;assert diff<1e-4,(model,p.name,diff)
  consistency.append({'model':model,'image':p.name,'max_abs_diff':diff})
 assert obj.device=='cpu'
files=list((P/'models').rglob('*'));assert not any(f.suffix=='.engine' for f in files)
rows=load(P/'results/cpu_comparison.json');assert len(rows) in [9,10];assert all(r['device']=='cpu' and r['stability']['iterations']==1000 for r in rows)
# Recheck baseline and selected deployment in fresh isolated processes.
for name,model,mode in [('baseline','models/a2_original.pt','LATENCY'),('selected',rec['model'],rec['ov_mode'] or 'LATENCY')]:
 old=P/'results'/('repeat_'+name+'.json')
 if old.exists() and load(old)['model']==model:continue
 subprocess.run([sys.executable,str(P/'scripts/repeat_cpu.py'),'--model',model,'--ov-mode',mode,'--out','results/repeat_'+name+'.json'],check=True)
# Native CPU evaluator is an independent metric cross-check; no hardware switch.
if not (P/'results/native_a2_original.json').exists():subprocess.run([sys.executable,str(P/'scripts/native_val.py'),'--models','models/a2_original.pt'],check=True)
subprocess.run([sys.executable,str(P/'scripts/native_val.py'),'--models',rec['model'],'--imgsz',str(d.profile.get('imgsz',640))],check=True)
proof={'passed':True,'device':'cpu','archive_verified_this_run':sha_source is not None,'source_sha256':sha_local,'dynamic_batch_shapes':shapes,'aspect_ratio_bounds':checks,'reused_CPU_prediction_checks':consistency,'measured_configs':len(rows),'source_hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (P/'scripts').glob('*.py')}}
(P/'results/verification_cpu.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print('CPU_VERIFY_OK',flush=True)
