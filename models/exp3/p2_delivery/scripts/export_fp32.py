from bootstrap import P
import torch,torchvision,onnx
from ultralytics import YOLO
torch.set_num_threads(4)
m=YOLO(str(P/'models/a2_original.pt')).model.cpu().float().eval();m.fuse(verbose=False)
h=m.model[-1];h.export=True;h.format='onnx';h.dynamic=True
with torch.inference_mode():torch.onnx.export(m,torch.zeros(1,3,640,640),str(P/'models/a2_fp32.onnx'),opset_version=17,input_names=['images'],output_names=['output0'],dynamic_axes={'images':{0:'batch'},'output0':{0:'batch'}},dynamo=False)
onnx.checker.check_model(onnx.load(P/'models/a2_fp32.onnx'));print('FP32_CPU_EXPORT_OK')
