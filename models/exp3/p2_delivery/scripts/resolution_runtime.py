from bootstrap import P
from cpu_runtime import Detector as BaseDetector
from pathlib import Path
import json,numpy as np,cv2
class Detector(BaseDetector):
 def __init__(self,model_path,device='cpu',ov_mode='LATENCY',conf=.001,iou=.55,profile=None):
  f=Path(model_path);cfg=f.parent/'cpu_resolution_config.json'
  if profile is None and 'cpu_resolution' in f.name and cfg.exists():profile=json.loads(cfg.read_text())
  super().__init__(f,device='cpu',ov_mode=ov_mode,conf=conf,iou=iou,profile=profile)
 def letterbox_u8(self,im):
  size=self.profile.get('imgsz',640);h,w=im.shape[:2];r=min(size/h,size/w);nw,nh=round(w*r),round(h*r);dw=(size-nw)/2;dh=(size-nh)/2
  left,right=round(dw-.1),round(dw+.1);top,bottom=round(dh-.1),round(dh+.1)
  out=cv2.copyMakeBorder(cv2.resize(im,(nw,nh)),top,bottom,left,right,cv2.BORDER_CONSTANT,value=(114,114,114))
  return np.ascontiguousarray(out[...,::-1].transpose(2,0,1)),(r,left,top,w,h)
 def letterbox(self,im):
  x,meta=self.letterbox_u8(im);return x.astype(np.float32)/255,meta
