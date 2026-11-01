from bootstrap import P
from pathlib import Path
import argparse,json,numpy as np,cv2
from resolution_runtime import Detector
q=argparse.ArgumentParser();q.add_argument('--model',required=True);q.add_argument('--image',required=True);q.add_argument('--out',required=True);q.add_argument('--conf',type=float,default=.25);q.add_argument('--ov-mode',choices=['LATENCY','THROUGHPUT'],default='LATENCY');a=q.parse_args()
im=cv2.imdecode(np.frombuffer(Path(a.image).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
if im is None:raise ValueError('Cannot decode image')
y=Detector(a.model,ov_mode=a.ov_mode,conf=a.conf)(im);Path(a.out).write_text(json.dumps(y.tolist()),encoding='utf-8');print(len(y),'detections; CPU only')
