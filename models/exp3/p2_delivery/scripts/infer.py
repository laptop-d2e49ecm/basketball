"""CPU detector: BGR -> original-coordinate Nx6 boxes. PT/ORT/OpenVINO."""
from bootstrap import P
from pathlib import Path
import argparse,json
import numpy as np,cv2,torch,torchvision
from ultralytics.utils.nms import non_max_suppression

def shared_nms(y,conf=.001,iou=.55):
 return non_max_suppression(y.float(),conf_thres=conf,iou_thres=iou,nc=1,agnostic=True,max_det=100,max_time_img=5)

class Detector:
 def __init__(self,model_path,device='cpu',ov_mode='LATENCY',conf=.001,iou=.55):
  if device not in [None,'cpu']:raise ValueError('This delivery only supports CPU')
  self.path=Path(model_path);self.kind=self.path.suffix.lower();self.device='cpu';self.conf=conf;self.iou=iou
  torch.set_num_threads(4);cv2.setNumThreads(1)
  if self.kind=='.pt':
   from ultralytics import YOLO
   self.model=YOLO(str(self.path)).model.cpu().float().eval()
  elif self.kind=='.onnx':
   import onnxruntime as ort
   opt=ort.SessionOptions();opt.intra_op_num_threads=4;opt.inter_op_num_threads=1;opt.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
   self.session=ort.InferenceSession(str(self.path),sess_options=opt,providers=['CPUExecutionProvider']);self.input=self.session.get_inputs()[0].name
  elif self.kind=='.xml':
   import openvino as ov
   self.core=ov.Core();self.compiled=self.core.compile_model(str(self.path),'CPU',{'PERFORMANCE_HINT':ov_mode,'INFERENCE_NUM_THREADS':4,'INFERENCE_PRECISION_HINT':'f32'});self.request=self.compiled.create_infer_request()
  else:raise ValueError('CPU model format must be .pt, .onnx or .xml')
 @torch.inference_mode()
 def raw(self,x):
  x=np.ascontiguousarray(x,dtype=np.float32)
  if self.kind=='.onnx':return torch.from_numpy(self.session.run(None,{self.input:x})[0])
  if self.kind=='.xml':return torch.from_numpy(np.array(self.request.infer({'images':x})[self.compiled.output(0)],copy=True))
  y=self.model(torch.from_numpy(x));return y[0] if isinstance(y,tuple) else y
 def tensor_batch(self,x):return [a.numpy() for a in shared_nms(self.raw(x),self.conf,self.iou)]
 @staticmethod
 def letterbox_u8(im):
  h,w=im.shape[:2];r=min(640/h,640/w);nw,nh=round(w*r),round(h*r);dw=(640-nw)/2;dh=(640-nh)/2
  left,right=round(dw-.1),round(dw+.1);top,bottom=round(dh-.1),round(dh+.1)
  out=cv2.copyMakeBorder(cv2.resize(im,(nw,nh)),top,bottom,left,right,cv2.BORDER_CONSTANT,value=(114,114,114))
  return np.ascontiguousarray(out[...,::-1].transpose(2,0,1)),(r,left,top,w,h)
 @staticmethod
 def letterbox(im):
  x,meta=Detector.letterbox_u8(im);return x.astype(np.float32)/255,meta
 def predict_batch(self,imgs):
  data=[self.letterbox(im) for im in imgs];out=self.tensor_batch(np.stack([d[0] for d in data]))
  for a,(_,meta) in zip(out,data):
   r,dx,dy,w,h=meta;a[:,[0,2]]=(a[:,[0,2]]-dx)/r;a[:,[1,3]]=(a[:,[1,3]]-dy)/r;a[:,[0,2]]=a[:,[0,2]].clip(0,w);a[:,[1,3]]=a[:,[1,3]].clip(0,h)
  return out
 def __call__(self,img_bgr):return self.predict_batch([img_bgr])[0]
if __name__=='__main__':
 q=argparse.ArgumentParser();q.add_argument('--model',required=True);q.add_argument('--image',required=True);q.add_argument('--out',required=True);q.add_argument('--conf',type=float,default=.25);a=q.parse_args()
 im=cv2.imdecode(np.frombuffer(Path(a.image).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
 if im is None:raise ValueError('Cannot decode image')
 y=Detector(a.model,conf=a.conf)(im);Path(a.out).write_text(json.dumps(y.tolist()),encoding='utf-8');print(len(y),'detections; CPU')
