from bootstrap import P
import torch,torchvision,onnx
from ultralytics import YOLO
class HalfGraph(torch.nn.Module):
 def __init__(self):
  super().__init__();self.net=YOLO(str(P/'models/a2_distilled.pt')).model.float().eval();self.net.fuse(verbose=False);self.net.half();h=self.net.model[-1];h.export=True;h.format='onnx';h.dynamic=True
 def forward(self,x):return self.net(x.half()).float()
torch.set_num_threads(4);export_device='cuda' if torch.cuda.is_available() else 'cpu';m=HalfGraph().to(export_device).eval()
with torch.inference_mode():torch.onnx.export(m,torch.zeros(1,3,640,640,device=export_device),str(P/'models/a2_distilled_fp16.onnx'),opset_version=17,input_names=['images'],output_names=['output0'],dynamic_axes={'images':{0:'batch'},'output0':{0:'batch'}},dynamo=False)
onnx.checker.check_model(onnx.load(P/'models/a2_distilled_fp16.onnx'));print('NATIVE_FP16_EXPORT_OK',flush=True)
