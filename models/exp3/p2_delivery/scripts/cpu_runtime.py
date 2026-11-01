"""CPU execution profile. A tuned file uses its adjacent CPU configuration."""
from bootstrap import P
from pathlib import Path
import json,numpy as np,torch
from infer import Detector as ReferenceDetector
class Detector(ReferenceDetector):
 def __init__(self,model_path,device='cpu',ov_mode='LATENCY',conf=.001,iou=.55,profile=None):
  f=Path(model_path);config=f.parent/'cpu_tuned_config.json'
  if profile is None and ('cpu_tuned' in f.as_posix()) and config.exists():profile=json.loads(config.read_text())
  self.profile=profile or {'threads':4,'mode':ov_mode,'fused_channels_last':False}
  super().__init__(f,device='cpu',ov_mode=self.profile.get('mode',ov_mode),conf=conf,iou=iou)
  threads=self.profile.get('threads',4);torch.set_num_threads(threads)
  if self.kind=='.pt' and self.profile.get('fused_channels_last'):
   self.model.fuse(verbose=False);self.model.to(memory_format=torch.channels_last)
  if threads!=4 and self.kind=='.onnx':
   import onnxruntime as ort
   o=ort.SessionOptions();o.intra_op_num_threads=threads;o.inter_op_num_threads=1;o.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_ALL
   self.session=ort.InferenceSession(str(f),sess_options=o,providers=['CPUExecutionProvider']);self.input=self.session.get_inputs()[0].name
  if threads!=4 and self.kind=='.xml':
   self.compiled=self.core.compile_model(str(f),'CPU',{'PERFORMANCE_HINT':self.profile.get('mode',ov_mode),'INFERENCE_NUM_THREADS':threads,'INFERENCE_PRECISION_HINT':'f32'});self.request=self.compiled.create_infer_request()
 @torch.inference_mode()
 def raw(self,x):
  if self.kind=='.pt' and self.profile.get('fused_channels_last'):
   y=self.model(torch.from_numpy(np.ascontiguousarray(x,dtype=np.float32)).contiguous(memory_format=torch.channels_last));return y[0] if isinstance(y,tuple) else y
  return super().raw(x)
