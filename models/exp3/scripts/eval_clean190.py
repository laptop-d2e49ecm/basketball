# -*- coding: utf-8 -*-
"""实验3 P1：干净口径重评（test 380 中的 190 张原始帧，剔除 _aug0 标注噪声副本）.

背景：scripts/03_augment 的 torchvision v2 调用只变换了标注框、图像原样返回，
全部 _aug0 副本 = 原图 + 错位标注（详见 exp3/README_HANDOFF.md 第六节）。
全集 test 380 的 mAP50 因此被腰斩（0.419）；本脚本在 190 张原始帧上重评：

  part=table  表1 的 10 个模型版本（ultralytics val，conf=0.001/iou=0.7/max_det=100）
              -> exp3/results/table1_clean190.json
  part=detail 量化误差细粒度分析（fp32 vs INT8 E1：分层 AP / 逐图 ΔAP / 噪声）
              -> exp3/results/eval_detail_clean190.json

用法（项目根目录）：
  python exp3/scripts/eval_clean190.py table
  python exp3/scripts/eval_clean190.py detail
"""
import glob
import json
import os
import sys

import numpy as np
import onnxruntime as ort
import torch
import torchvision

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_detail as ED

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG_DIR = os.path.join(ROOT, "data/splits/yolo/images/test")
SUBSET_DIR = os.path.join(ROOT, "exp3/p2_check")
YAML190 = os.path.join(SUBSET_DIR, "yaml190.yaml")
TXT190 = os.path.join(SUBSET_DIR, "test190.txt")

MODELS = [
    ("A2 (PyTorch FP32)", "exp3/models/a2.pt"),
    ("A2 (ONNX FP32)", "exp3/models/a2_fp32.onnx"),
    ("INT8 E1 (val346)", "exp3/models/a2_int8_val346.onnx"),
    ("INT8 E2 (train500)", "exp3/models/a2_int8_train500.onnx"),
    ("INT8 E4 (per-channel)", "exp3/models/a2_int8_val346_pc.onnx"),
    ("A2 蒸馏 dis=3", "exp3/models/a2_distill_dis3.pt"),
    ("A2 蒸馏 dis=6", "exp3/models/a2_distilled.pt"),
    ("A2 蒸馏 dis=9", "exp3/models/a2_distill_dis9.pt"),
    ("A2 蒸馏+INT8", "exp3/models/a2_distilled_int8.onnx"),
    ("M1 教师 (YOLOv8m)", "models/exp2/A2_yolov8m/weights/best.pt"),
]


def clean_files():
    return sorted(f for f in os.listdir(IMG_DIR) if "_aug0" not in f and f.lower().endswith(".jpg"))


def write_subset():
    os.makedirs(SUBSET_DIR, exist_ok=True)
    files = clean_files()
    with open(TXT190, "w") as f:
        for n in files:
            f.write(os.path.join(IMG_DIR, n).replace("\\", "/") + "\n")
    with open(YAML190, "w") as f:
        f.write("path: data/splits/yolo\ntrain: " + TXT190.replace("\\", "/")
                + "\nval: " + TXT190.replace("\\", "/")
                + "\ntest: " + TXT190.replace("\\", "/") + "\nnames:\n  0: player\n")
    return files


def part_table():
    from ultralytics import YOLO
    write_subset()
    out = {}
    for tag, rel in MODELS:
        p = os.path.join(ROOT, rel)
        r = YOLO(p).val(data=YAML190, split="test", imgsz=640, batch=16, device="cpu",
                        conf=0.001, iou=0.7, max_det=100, verbose=False, plots=False)
        out[tag] = {"model": rel, "map50": round(float(r.box.map50), 4),
                    "map50_95": round(float(r.box.map), 4),
                    "P": round(float(r.box.mp), 4), "R": round(float(r.box.mr), 4)}
        print(f"{tag:22s} mAP50={out[tag]['map50']:.4f}  mAP50-95={out[tag]['map50_95']:.4f}"
              f"  P={out[tag]['P']:.4f}  R={out[tag]['R']:.4f}", flush=True)
    dst = os.path.join(ROOT, "exp3/results/table1_clean190.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("saved ->", dst)


def part_detail():
    files = write_subset()
    paths = [os.path.join(IMG_DIR, f) for f in files]
    gt_by_img = [ED.load_gt(p) for p in paths]
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = {"fp32": ort.InferenceSession(os.path.join(ROOT, "exp3/models/a2_fp32.onnx"), so, providers=["CPUExecutionProvider"]),
            "int8": ort.InferenceSession(os.path.join(ROOT, "exp3/models/a2_int8_val346.onnx"), so, providers=["CPUExecutionProvider"])}
    rng = np.random.default_rng(42)

    P = {"fp32": [], "int8": [], "fp32_noise": [], "int8_noise": []}
    for i, p in enumerate(paths):
        inp = ED.preprocess(p)
        for tag in ("fp32", "int8"):
            P[tag].append(ED.predict(sess[tag], inp))
        if i % 50 == 0:
            print(f"[{i+1}/{len(paths)}]", flush=True)
    for i, p in enumerate(paths):  # 噪声轮（同一 rng 顺序，两模型输入完全一致）
        inp = ED.preprocess(p, 0.02, rng)
        for tag in ("fp32", "int8"):
            P[f"{tag}_noise"].append(ED.predict(sess[tag], inp))

    out = {k: ED.eval_all(v, gt_by_img) for k, v in P.items()}
    delta = np.array([ED.per_image_ap(a, g[0]) - ED.per_image_ap(b, g[0])
                      for a, b, g in zip(P["fp32"], P["int8"], gt_by_img)])
    out["per_image_delta_ap"] = {
        "mean": float(delta.mean()), "std": float(delta.std()),
        "min": float(delta.min()), "max": float(delta.max()),
        "hist": np.histogram(delta, bins=10, range=(-1, 1))[0].tolist(),
        "worst_images": [paths[i] for i in np.argsort(np.abs(delta))[-5:]],
    }
    dst = os.path.join(ROOT, "exp3/results/eval_detail_clean190.json")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\n{'':12s}{'mAP50':>8s}{'small':>8s}{'medium':>8s}{'large':>8s}")
    for k in ("fp32", "int8", "fp32_noise", "int8_noise"):
        r = out[k]
        f3 = lambda v: f"{v:8.3f}" if v is not None else f"{'--':>8s}"
        print(f"{k:12s}{f3(r['map50'])}{f3(r['ap50_small'])}{f3(r['ap50_medium'])}{f3(r['ap50_large'])}")
    print(f"GT 分布: 小 {out['fp32']['n_gt_small']} / 中 {out['fp32']['n_gt_medium']} / 大 {out['fp32']['n_gt_large']}")
    print("saved ->", dst)


if __name__ == "__main__":
    {"table": part_table, "detail": part_detail}[sys.argv[1]]()
