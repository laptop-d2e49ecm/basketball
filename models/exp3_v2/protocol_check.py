# -*- coding: utf-8 -*-
"""协议核查：A2′ 的 PyTorch 与 ONNX FP32 在 test 190 上差 0.1–0.2pp 的来源。

结论由两项实测给出：
1. 数值等价：同一输入张量上 .pt 与 a2v2_fp32.onnx 原始输出 (1,5,8400) 框差 <0.002px、得分差 <1e-5；
2. 协议差异：ultralytics 对 .pt 默认 rect=True，640×640 图按 stride 补边到 672×672 推理；
   静态 ONNX 固定 640×640（等价 rect=False）。.pt 改用 rect=False 即与 ONNX 结果逐位一致。
因此表中 PyTorch 行（rect=True）与 ONNX 行（640 输入）不跨行比较 0.1pp 级差异；
量化代价一律 ONNX 对 ONNX 计算，不受影响。
用法：.venv/Scripts/python.exe models/exp3_v2/protocol_check.py → models/exp3_v2/protocol_check.json
"""
import glob
import json
import os

import cv2
import numpy as np
import onnxruntime as ort
import torch
from ultralytics import YOLO

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PT = os.path.join(ROOT, "models/exp2_v2/A2_yolov8n/weights/best.pt")
ONNX = os.path.join(ROOT, "models/exp3_v2/models/a2v2_fp32.onnx")
DATA = os.path.join(ROOT, "data/splits/yolo/data_clean.yaml")
KW = dict(data=DATA, split="test", imgsz=640, device="cpu", conf=0.001, iou=0.7, max_det=100,
          verbose=False, plots=False)


def metrics(r):
    return {"P": round(float(r.box.mp), 4), "R": round(float(r.box.mr), 4),
            "map50": round(float(r.box.map50), 4), "map50_95": round(float(r.box.map), 4)}


def main():
    pt = YOLO(PT).model.float().eval()
    sess = ort.InferenceSession(ONNX, providers=["CPUExecutionProvider"])
    box_d, score_d = [], []
    for p in sorted(glob.glob(os.path.join(ROOT, "data/splits/yolo/images/test/*.jpg")))[::19]:
        x = np.ascontiguousarray((cv2.imread(p)[:, :, ::-1].transpose(2, 0, 1) / 255.0)[None].astype(np.float32))
        with torch.no_grad():
            a = pt(torch.from_numpy(x))[0].numpy()
        b = sess.run(None, {"images": x})[0]
        box_d.append(float(np.abs(a[0, :4] - b[0, :4]).max()))
        score_d.append(float(np.abs(a[0, 4] - b[0, 4]).max()))
    out = {"raw_output_equivalence": {"n_images": len(box_d), "max_abs_box_px": round(max(box_d), 5),
                                      "max_abs_score": round(max(score_d), 7)}}
    out["pt_rect_true_default"] = metrics(YOLO(PT).val(batch=16, **KW))
    out["pt_rect_false_640"] = metrics(YOLO(PT).val(batch=16, rect=False, **KW))
    out["onnx_fp32_640"] = metrics(YOLO(ONNX).val(batch=16, **KW))
    out["pt_rect_false_equals_onnx"] = out["pt_rect_false_640"] == out["onnx_fp32_640"]
    with open(os.path.join(ROOT, "models/exp3_v2/protocol_check.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
