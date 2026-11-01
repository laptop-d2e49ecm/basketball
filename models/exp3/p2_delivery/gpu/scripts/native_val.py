from bootstrap import P,STAGE1,SOURCE_ROOT
import argparse,json
from pathlib import Path
import torch,torchvision
from ultralytics import YOLO
from ultralytics.data import utils as data_utils
# Plotting is disabled; use an existing system font to avoid irrelevant downloads.
data_utils.check_font=lambda *args,**kwargs: Path("C:/Windows/Fonts/arial.ttf")
(P.parent/'data/data.yaml').write_text('path: '+(P.parent/'data').as_posix()+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames: {0: player}\n',encoding='utf-8')
q=argparse.ArgumentParser();q.add_argument('--models',required=True);q.add_argument('--device',default='cpu');a=q.parse_args();rows=[];torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
for fn in a.models.split(','):
 f=P/fn;tag=f.stem if f.suffix!='.xml' else f.parent.name
 m=YOLO(str(f),task='detect')
 r=m.val(data=str(P.parent/'data/data.yaml'),split='test',imgsz=640,batch=4,conf=.001,iou=.55,max_det=100,device=a.device,half=False,rect=False,plots=False,save_json=False,workers=0,project=str(P/'results/native'),name=tag,exist_ok=True,verbose=False)
 row={'model':fn,'native_ultralytics':r.results_dict,'speed':r.speed,'protocol':{'split':'clean original test190','batch':4,'imgsz':640,'conf':.001,'iou':.55,'max_det':100,'rect':False},'note':'Ultralytics native metric; keep separate from pycocotools COCOeval and custom AP'};rows.append(row)
 (P/'results'/('native_'+tag+'.json')).write_text(json.dumps(row,indent=2),encoding='utf-8');print('NATIVE_DONE',tag,r.results_dict,flush=True)
