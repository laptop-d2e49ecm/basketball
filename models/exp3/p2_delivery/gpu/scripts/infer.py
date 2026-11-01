"""Common detector: BGR numpy image -> Nx6 xyxy,confidence,class in original coordinates.
Backends: .pt (PyTorch), .onnx (ORT CPU), .xml (OpenVINO CPU), .engine (TensorRT GPU).
All use identical letterbox/NMS. Thread safety: one instance per worker.
"""
from bootstrap import P,STAGE1,SOURCE_ROOT
import argparse,json,sys
from pathlib import Path
import numpy as np,cv2,torch,torchvision
from ultralytics.utils.nms import non_max_suppression

def shared_nms(y,conf=.001,iou=.55):
 return non_max_suppression(y.float(),conf_thres=conf,iou_thres=iou,nc=1,agnostic=True,max_det=100,max_time_img=5)

def make_graph_backend(path):
 sys.path.insert(0,str(STAGE1/'code'))
 import experiment
 experiment.P=STAGE1
 previous=experiment.load_model
 def load_any(fused=False):
  from ultralytics import YOLO
  m=YOLO(str(path)).model.float().eval();m.model[-1].end2end=False
  if fused:m.fuse(verbose=False)
  return m
 experiment.load_model=load_any
 try:return experiment.Backend('torch_gpu_fused_fp16_graph')
 finally:experiment.load_model=previous

class Detector:
 def __init__(self,model_path,device=None,ov_mode='LATENCY',conf=.001,iou=.55,graph=False):
  self.path=Path(model_path);self.conf=conf;self.iou=iou;self.kind=self.path.suffix.lower();self.device=device or ('cuda' if self.kind in ['.pt','.engine'] and torch.cuda.is_available() else 'cpu');self.buffers={}
  if graph:
   assert self.device=='cuda' and self.kind=='.pt'
   self.b=make_graph_backend(self.path);self.kind='.graph'
  elif self.kind=='.pt':
   from ultralytics import YOLO
   self.model=YOLO(str(self.path)).model.to(self.device).float().eval();self.dtype=torch.float32
  elif self.kind=='.onnx':
   import onnxruntime as ort
   o=ort.SessionOptions();o.intra_op_num_threads=4;o.inter_op_num_threads=1;o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
   self.session=ort.InferenceSession(str(self.path),sess_options=o,providers=['CPUExecutionProvider']);self.input=self.session.get_inputs()[0].name
  elif self.kind=='.xml':
   import openvino as ov
   self.core=ov.Core();self.compiled=self.core.compile_model(str(self.path),'CPU',{'PERFORMANCE_HINT':ov_mode,'INFERENCE_NUM_THREADS':4,'INFERENCE_PRECISION_HINT':'f32'});self.request=self.compiled.create_infer_request()
  elif self.kind=='.engine':
   import tensorrt as trt
   self.trt=trt;self.logger=trt.Logger(trt.Logger.WARNING);self.runtime=trt.Runtime(self.logger);self.engine=self.runtime.deserialize_cuda_engine(self.path.read_bytes());assert self.engine;self.context=self.engine.create_execution_context();self.stream=torch.cuda.Stream(device=self.device)
   self.input=next(self.engine.get_tensor_name(i) for i in range(self.engine.num_io_tensors) if self.engine.get_tensor_mode(self.engine.get_tensor_name(i))==trt.TensorIOMode.INPUT)
   self.output=next(self.engine.get_tensor_name(i) for i in range(self.engine.num_io_tensors) if self.engine.get_tensor_mode(self.engine.get_tensor_name(i))==trt.TensorIOMode.OUTPUT)
   self.dtype=torch.float16 if self.engine.get_tensor_dtype(self.input)==trt.float16 else torch.float32
  else:raise ValueError('unsupported model '+str(self.path))
 @torch.inference_mode()
 def raw(self,x):
  if self.kind=='.graph':return self.b.forward(self.b.prepare(x))
  if self.kind=='.onnx':return torch.from_numpy(self.session.run(None,{self.input:np.ascontiguousarray(x,dtype=np.float32)})[0])
  if self.kind=='.xml':return torch.from_numpy(np.array(self.request.infer({'images':x})[self.compiled.output(0)],copy=True))
  t=torch.from_numpy(x).to(self.device,dtype=self.dtype)
  if self.kind=='.pt':
   y=self.model(t);return y[0] if isinstance(y,tuple) else y
  self.context.set_input_shape(self.input,tuple(t.shape));self.context.set_tensor_address(self.input,t.data_ptr());shape=tuple(self.context.get_tensor_shape(self.output));key=(shape,str(self.engine.get_tensor_dtype(self.output)))
  if key not in self.buffers:self.buffers[key]=torch.empty(shape,device=self.device,dtype=torch.float16 if self.engine.get_tensor_dtype(self.output)==self.trt.float16 else torch.float32)
  y=self.buffers[key];self.context.set_tensor_address(self.output,y.data_ptr());current=torch.cuda.current_stream(device=self.device);self.stream.wait_stream(current);assert self.context.execute_async_v3(self.stream.cuda_stream);t.record_stream(self.stream);y.record_stream(self.stream);current.wait_stream(self.stream);return y
 def tensor_batch(self,x):
  y=self.raw(x).float()
  return [a.float().cpu().numpy() for a in shared_nms(y,self.conf,self.iou)]
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
 q=argparse.ArgumentParser();q.add_argument('--model',required=True);q.add_argument('--image',required=True);q.add_argument('--out',required=True);q.add_argument('--device');q.add_argument('--graph',action='store_true');q.add_argument('--pipeline',action='store_true');q.add_argument('--conf',type=float,default=.25);a=q.parse_args();cls=__import__('optimized_trt').Detector if a.pipeline else Detector;d=cls(a.model,device=a.device,graph=a.graph,conf=a.conf);y=d(cv2.imread(a.image));Path(a.out).write_text(json.dumps(y.tolist()),encoding='utf-8');print(len(y),'detections')
