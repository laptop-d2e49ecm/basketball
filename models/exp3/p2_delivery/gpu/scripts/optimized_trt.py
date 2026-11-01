"""TensorRT pipeline: pooled uint8 preprocessing, GPU normalization and persistent CUDA buffers."""
from bootstrap import P
import numpy as np,torch
from concurrent.futures import ThreadPoolExecutor
from infer import Detector as Reference,shared_nms
class Detector(Reference):
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs)
  if self.kind!='.engine':raise ValueError('optimized runtime requires a real TensorRT engine')
  self.pool=ThreadPoolExecutor(max_workers=4)
  self.inputs={}
 @torch.inference_mode()
 def execute(self,t):
  self.context.set_input_shape(self.input,tuple(t.shape));self.context.set_tensor_address(self.input,t.data_ptr())
  shape=tuple(self.context.get_tensor_shape(self.output));key=(shape,str(self.engine.get_tensor_dtype(self.output)))
  if key not in self.buffers:self.buffers[key]=torch.empty(shape,device=self.device,dtype=torch.float16 if self.engine.get_tensor_dtype(self.output)==self.trt.float16 else torch.float32)
  y=self.buffers[key];self.context.set_tensor_address(self.output,y.data_ptr());current=torch.cuda.current_stream(device=self.device)
  self.stream.wait_stream(current)
  if not self.context.execute_async_v3(self.stream.cuda_stream):raise RuntimeError('TensorRT execution failed')
  t.record_stream(self.stream);y.record_stream(self.stream);current.wait_stream(self.stream)
  return y
 @torch.inference_mode()
 def predict_prepared(self,data):
  x=np.stack([d[0] for d in data]);shape=tuple(x.shape)
  if shape not in self.inputs:self.inputs[shape]=(torch.empty(shape,dtype=torch.uint8,device='cuda'),torch.empty(shape,dtype=self.dtype,device='cuda'))
  u,t=self.inputs[shape];u.copy_(torch.from_numpy(x));t.copy_(u);t.div_(255.)
  out=[a.float().cpu().numpy() for a in shared_nms(self.execute(t),self.conf,self.iou)]
  for a,(_,meta) in zip(out,data):
   r,dx,dy,w,h=meta;a[:,[0,2]]=(a[:,[0,2]]-dx)/r;a[:,[1,3]]=(a[:,[1,3]]-dy)/r;a[:,[0,2]]=a[:,[0,2]].clip(0,w);a[:,[1,3]]=a[:,[1,3]].clip(0,h)
  return out
 def predict_batch(self,imgs):
  data=list(self.pool.map(self.letterbox_u8,imgs)) if len(imgs)>1 else [self.letterbox_u8(imgs[0])]
  return self.predict_prepared(data)
 def close(self):self.pool.shutdown(wait=True)
