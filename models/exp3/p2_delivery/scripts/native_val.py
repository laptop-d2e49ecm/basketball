from bootstrap import P
import argparse,json,shutil,hashlib
from pathlib import Path
import torch,torchvision
from ultralytics import YOLO
from ultralytics.data import utils as data_utils
# Plotting is disabled; use an existing system font to avoid irrelevant downloads.
data_utils.check_font=lambda *args,**kwargs: Path("C:/Windows/Fonts/arial.ttf")
(P/'data/data.yaml').write_text('path: '+(P/'data').as_posix()+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames: {0: player}\n',encoding='utf-8')
q=argparse.ArgumentParser();q.add_argument('--models',required=True);q.add_argument('--imgsz',type=int,default=640);a=q.parse_args();rows=[];torch.set_num_threads(4);
for fn in a.models.split(','):
 f=P/fn;tag=f.stem if f.suffix!='.xml' else f.parent.name
 input_path=f;alias_proof=None
 if f.suffix=='.xml':
  # Ultralytics detects OpenVINO through the standard export-directory suffix.
  wrapper=P/'results/native_input'/(tag+'_openvino_model');wrapper.mkdir(parents=True,exist_ok=True)
  for source in [f,f.with_suffix('.bin')]:shutil.copy2(source,wrapper/source.name)
  (wrapper/'metadata.yaml').write_text('task: detect\nstride: 32\nbatch: 4\nimgsz: [640, 640]\nnames: {0: player}\nargs: {dynamic: true, nms: false}\n',encoding='utf-8')
  alias_proof={source.name:hashlib.sha256(source.read_bytes()).hexdigest() for source in [f,f.with_suffix('.bin')]}
  assert all(hashlib.sha256((wrapper/name).read_bytes()).hexdigest()==digest for name,digest in alias_proof.items())
  input_path=wrapper
  import openvino as ov
  OriginalCore=ov.Core
  class CPUCore(OriginalCore):
   def compile_model(self,model,*args,**kwargs):
    kwargs['device_name']='CPU';cfg=dict(kwargs.get('config') or {});cfg.update({'INFERENCE_NUM_THREADS':4,'INFERENCE_PRECISION_HINT':'f32'});kwargs['config']=cfg
    return super().compile_model(model,**kwargs)
  ov.Core=CPUCore
 m=YOLO(str(input_path),task='detect')
 r=m.val(data=str(P/'data/data.yaml'),split='test',imgsz=a.imgsz,batch=4,conf=.001,iou=.55,max_det=100,device="cpu",half=False,rect=False,plots=False,save_json=False,workers=0,project=str(P/'results/native'),name=tag,exist_ok=True,verbose=False)
 row={'model':fn,'CPU_validation_alias_sha256':alias_proof,'device':'cpu','native_ultralytics':r.results_dict,'speed':r.speed,'protocol':{'split':'clean original test190','batch':4,'imgsz':a.imgsz,'conf':.001,'iou':.55,'max_det':100,'rect':False},'note':'Ultralytics native metric; keep separate from pycocotools COCOeval and custom AP'};rows.append(row)
 (P/'results'/('native_'+tag+'.json')).write_text(json.dumps(row,indent=2),encoding='utf-8');print('NATIVE_DONE',tag,r.results_dict,flush=True)
