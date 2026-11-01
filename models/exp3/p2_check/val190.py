# -*- coding: utf-8 -*-
"""用项目自己的 ultralytics 在 P2 的 190 张原始帧子集上验证 A2（与实验2终评同口径）。"""
import json
from ultralytics import YOLO

m = YOLO("exp3/models/a2.pt")
r = m.val(data="exp3/p2_check/yaml190.yaml", split="test", imgsz=640, batch=16,
          device="cpu", conf=0.001, iou=0.7, max_det=100, verbose=False, plots=False)
out = {
    "map50": float(r.box.map50), "map50_95": float(r.box.map95),
    "P": float(r.box.mp), "R": float(r.box.mr),
    "note": "A2 a.pt, ultralytics 8.4.176, P2 test190(原始帧), conf=0.001 iou=0.7",
}
print(json.dumps(out, indent=1))
json.dump(out, open("exp3/p2_check/result190.json", "w"))
