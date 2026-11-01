# -*- coding: utf-8 -*-
"""A1（无增强消融组）vs A2（含增强）在干净 190 帧上的对比——回答"增强 bug 是否毁了训练"。"""
import json
from ultralytics import YOLO

r = YOLO("models/exp2/A1_yolov8n/weights/best.pt").val(
    data="exp3/p2_check/yaml190.yaml", split="test", imgsz=640, batch=16,
    device="cpu", conf=0.001, iou=0.7, max_det=100, verbose=False, plots=False)
out = {"model": "A1 (原始帧2158, 无增强)", "map50": round(float(r.box.map50), 4),
       "map50_95": round(float(r.box.map), 4), "P": round(float(r.box.mp), 4), "R": round(float(r.box.mr), 4)}
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open("exp3/results/a1_clean190.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
