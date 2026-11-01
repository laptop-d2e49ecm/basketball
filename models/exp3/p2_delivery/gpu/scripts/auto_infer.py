"""GPU-first deployment for the same original A2 weights; OpenVINO CPU fallback."""
from bootstrap import P
from pathlib import Path
import torch
from optimized_trt import Detector as TRTDetector
from infer import Detector as ReferenceDetector
class AutoDetector:
 def __init__(self,prefer_gpu=True,conf=.25,iou=.55):
  if prefer_gpu and torch.cuda.is_available():
   self.backend='TensorRT GPU pipeline';self.detector=TRTDetector(P/'models/a2_trt_fp16.engine',device='cuda',conf=conf,iou=iou)
  else:
   self.backend='OpenVINO CPU';self.detector=ReferenceDetector(P.parent/'models/a2_cpu_tuned/model.xml',device='cpu',conf=conf,iou=iou)
 def __call__(self,img_bgr):return self.detector(img_bgr)
 def predict_batch(self,images):return self.detector.predict_batch(images)
