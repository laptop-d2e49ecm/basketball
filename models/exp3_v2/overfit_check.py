# -*- coding: utf-8 -*-
"""过拟合检查：A2′ 在训练集原始帧子集（200 张，见过）与 test 190（没见过）上的同口径对比。

判据：训练/测试差距小 → 未过拟合（高分来自任务本身易：单类、近景、同源视频）；
差距大 → 记忆训练集。评测参数与 models/exp2_v2/eval_test190.py 一致。
用法：.venv/Scripts/python.exe models/exp3_v2/overfit_check.py
输出：models/exp3_v2/overfit_check.json
"""
import json
import os

from ultralytics import YOLO

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W = os.path.join(ROOT, "models/exp2_v2/A2_yolov8n/weights/best.pt")
SCOPES = {  # (yaml, split, 图片清单)
    "train200_seen": (os.path.join(ROOT, "models/exp3_v2/yaml_train200.yaml"), "val",
                      os.path.join(ROOT, "models/exp3_v2/train200.txt")),  # 200 张原始训练帧
    "test190_unseen": (os.path.join(ROOT, "data/splits/yolo/data_clean.yaml"), "test",
                       os.path.join(ROOT, "data/splits/yolo/original_test.txt")),
}


def main():
    out = {"weights": "models/exp2_v2/A2_yolov8n/weights/best.pt (A2′)"}
    for name, (yaml, split, listing) in SCOPES.items():
        r = YOLO(W).val(data=yaml, split=split, imgsz=640, batch=16, device="cpu", conf=0.001,
                        iou=0.7, max_det=100, verbose=False, plots=False)
        n = sum(1 for line in open(listing, encoding="utf-8") if line.strip())
        out[name] = {"n_images": n, "P": round(float(r.box.mp), 4), "R": round(float(r.box.mr), 4),
                     "map50": round(float(r.box.map50), 4), "map50_95": round(float(r.box.map), 4)}
        print(name, out[name], flush=True)
    tr, te = out["train200_seen"], out["test190_unseen"]
    out["gap_pp"] = {k: round((tr[k] - te[k]) * 100, 2) for k in ("P", "R", "map50", "map50_95")}
    with open(os.path.join(ROOT, "models/exp3_v2/overfit_check.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("gap (train - test, pp):", out["gap_pp"])


if __name__ == "__main__":
    main()
