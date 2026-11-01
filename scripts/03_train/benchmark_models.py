# -*- coding: utf-8 -*-
"""实验 2 选型实证：目标检测模型家族对比（CPU 推理速度 + 零样本 person→player mAP50）。

目的：给"为什么选 YOLO"提供数据证据（口说无凭）。两类证据：
  ① 同批验证图上的单张推理耗时（CPU）——实时性（视频流场景）是选型第一约束；
  ② 各家族 COCO 预训练权重对我们 val 集（player 框）的零样本 mAP50（person→player）——
     迁移起点，说明"小样本 + 预训练微调"路线的可行性；真正的公平精度对比在微调后
     （train_yolo.py 的 A/B/C/D 组，上 GPU 跑）。

对比模型（全部官方 COCO 预训练，person 类）：
  YOLOv8n / YOLOv8s          ultralytics（本项目主选家族）
  Faster R-CNN R50-FPN       torchvision（两阶段代表）
  RetinaNet R50-FPN          torchvision（单阶段 Focal Loss 代表）
  SSD300-VGG16               torchvision（经典单阶段轻量代表）

用法：
    python scripts/03_train/benchmark_models.py [--n 120] [--out docs/EXP2_MODEL_SELECTION.md]
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
VAL_IMG = ROOT / "data/splits/yolo/images/val"
VAL_LBL = ROOT / "data/splits/yolo/labels/val"


# ---------- 评测工具：单类 mAP50（GT=player，预测取 person） ----------
def load_gt():
    gts = {}
    for img in sorted(VAL_IMG.glob("*.jpg")):
        lbl = VAL_LBL / (img.stem + ".txt")
        boxes = []
        if lbl.exists():
            W = H = 640  # 数据集已标准化为 640×640
            for line in lbl.read_text().splitlines():
                p = line.split()
                if len(p) == 5:
                    _, cx, cy, w, h = map(float, p)
                    boxes.append([(cx - w / 2) * W, (cy - h / 2) * H,
                                  (cx + w / 2) * W, (cy + h / 2) * H])
        gts[img.name] = np.array(boxes).reshape(-1, 4)
    return gts


def iou_matrix(a, b):
    """a:(N,4) b:(M,4) xyxy -> (N,M) IoU"""
    if len(a) == 0 or len(b) == 0:
        return np.zeros((len(a), len(b)))
    tl = np.maximum(a[:, None, :2], b[None, :, :2])
    br = np.minimum(a[:, None, 2:], b[None, :, 2:])
    inter = np.prod(np.clip(br - tl, 0, None), 2)
    area_a = np.prod(a[:, 2:] - a[:, :2], 1)
    area_b = np.prod(b[:, 2:] - b[:, :2], 1)
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


def map50(all_preds, gts):
    """all_preds: [(img_name, conf, xyxy)] 全图预测汇总 -> 单类 AP@0.5（全点插值）"""
    n_gt = sum(len(v) for v in gts.values())
    matched = {k: np.zeros(len(v), bool) for k, v in gts.items()}
    preds = sorted(all_preds, key=lambda p: -p[1])
    tp = np.zeros(len(preds))
    for i, (name, _, box) in enumerate(preds):
        gt, used = gts[name], matched[name]
        if len(gt):
            ious = iou_matrix(box[None], gt)[0]
            ious[used] = -1
            j = ious.argmax()
            if ious[j] >= 0.5:
                tp[i], used[j] = 1, True
    tp_cum, fp_cum = np.cumsum(tp), np.cumsum(1 - tp)
    recall = tp_cum / max(n_gt, 1)
    prec = tp_cum / np.maximum(tp_cum + fp_cum, 1)
    # 全点插值 AP（PR 曲线下面积，数值法）
    mrec = np.concatenate([[0], recall, [1]])
    mpre = np.concatenate([[0], prec, [0]])
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    return float(np.sum((mrec[1:] - mrec[:-1]) * mpre[1:]))


# ---------- 各家族推理封装：统一返回 [(img_name, conf, xyxy)] ----------
def bench_yolo(name, files):
    from ultralytics import YOLO
    model = YOLO(f"{name}.pt")
    preds, times = [], []
    for f in files:
        t0 = time.perf_counter()
        r = model.predict(str(f), imgsz=640, device="cpu", conf=0.01,
                          max_det=100, verbose=False)[0]
        times.append(time.perf_counter() - t0)
        keep = (r.boxes.cls.cpu().numpy() == 0)  # COCO person=0
        for b, cf in zip(r.boxes.xyxy.cpu().numpy()[keep],
                         r.boxes.conf.cpu().numpy()[keep]):
            preds.append((f.name, float(cf), b))
    return preds, times, sum(p.numel() for p in model.model.parameters())


def bench_torchvision(build, files, person_label=1):
    import torchvision.transforms.functional as TF
    model, _ = build()  # 预处理自行处理：640 原图直接输入（官方微调教程标准喂法）
    model.eval()
    preds, times = [], []
    with torch.no_grad():
        for f in files:
            img = Image.open(f).convert("RGB")
            t0 = time.perf_counter()
            x = TF.to_tensor(img)  # 0-1 张量，640×640；框输出即原图坐标
            out = model([x])[0]
            times.append(time.perf_counter() - t0)
            keep = out["labels"] == person_label  # torchvision COCO: person=1
            for b, cf in zip(out["boxes"][keep].numpy(), out["scores"][keep].numpy()):
                preds.append((f.name, float(cf), b))
    n_par = sum(p.numel() for p in model.parameters())
    return preds, times, n_par


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120, help="取前 N 张验证图（速度与精度同批）")
    ap.add_argument("--out", default="docs/EXP2_MODEL_SELECTION.md")
    args = ap.parse_args()

    files = sorted(VAL_IMG.glob("*.jpg"))[: args.n]
    gts = {k: v for k, v in load_gt().items() if k in {f.name for f in files}}
    print(f"验证图 {len(files)} 张，GT 框 {sum(len(v) for v in gts.values())} 个")

    from torchvision.models.detection import (FasterRCNN_ResNet50_FPN_Weights,
                                              RetinaNet_ResNet50_FPN_Weights,
                                              SSD300_VGG16_Weights)

    def faster():
        w = FasterRCNN_ResNet50_FPN_Weights.COCO_V1
        from torchvision.models.detection import fasterrcnn_resnet50_fpn
        m = fasterrcnn_resnet50_fpn(weights=w, box_score_thresh=0.01)
        return m, w.transforms()

    def retina():
        w = RetinaNet_ResNet50_FPN_Weights.COCO_V1
        from torchvision.models.detection import retinanet_resnet50_fpn
        m = retinanet_resnet50_fpn(weights=w, box_score_thresh=0.01)
        return m, w.transforms()

    def ssd():
        w = SSD300_VGG16_Weights.COCO_V1
        from torchvision.models.detection import ssd300_vgg16
        m = ssd300_vgg16(weights=w, score_thresh=0.01)
        return m, w.transforms()

    jobs = {
        "YOLOv8n(ultralytics)": lambda: bench_yolo("yolov8n", files),
        "YOLOv8s(ultralytics)": lambda: bench_yolo("yolov8s", files),
        "FasterRCNN-R50(torchvision)": lambda: bench_torchvision(faster, files),
        "RetinaNet-R50(torchvision)": lambda: bench_torchvision(retina, files),
        "SSD300-VGG16(torchvision)": lambda: bench_torchvision(ssd, files),
    }

    rows = []
    for name, fn in jobs.items():
        print(f"[RUN] {name} ...", flush=True)
        try:
            preds, times, n_par = fn()
            ms = 1000 * float(np.mean(times[max(3, len(times) // 10):]))  # 去掉前几帧冷启动
            ap = map50(preds, gts)
            rows.append({"model": name, "params_M": round(n_par / 1e6, 1),
                         "ms_per_img_cpu": round(ms, 1), "fps_cpu": round(1000 / ms, 1),
                         "zeroshot_map50": round(ap, 4), "n_pred": len(preds)})
            print(f"    {rows[-1]}", flush=True)
        except Exception as exc:  # noqa: BLE001 —— 单模型失败不影响其余对比
            rows.append({"model": name, "error": str(exc)[:200]})
            print(f"    [FAIL] {exc}", flush=True)

    out = ROOT / args.out
    cols = ["model", "params_M", "ms_per_img_cpu", "fps_cpu", "zeroshot_map50", "n_pred"]
    md = ["# 实验 2 选型实证：检测模型家族对比（本机 CPU）", "",
          f"> 数据：data/splits/yolo/val 前 {len(files)} 张（640×640，GT=player 框）；",
          "> 预测取各模型 COCO 预训练的 person 类输出（conf≥0.01）；",
          "> ms/img 为去掉冷启动后的均值；零样本 mAP50 = person→player 直接评（未微调）。",
          "> **注意：这是『迁移起点+速度』对比；公平的精度对比看微调后的 A/B/C/D 组（GPU）。", ""]
    md.append("| " + " | ".join(cols) + " |")
    md.append("|" + "---|" * len(cols))
    for r in rows:
        if "error" in r:
            md.append(f"| {r['model']} | 失败：{r['error']} | | | | |")
        else:
            md.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[OK] 结果表 -> {out}")
    print(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
