"""实验3 P1：量化误差细粒度分析（分层 AP / 逐图 ΔAP / 噪声鲁棒性）.

对比对象：a2_fp32.onnx vs a2_int8_val346.onnx，同一 ONNX Runtime CPU 引擎，
只隔离"量化"这一个变量。口径：
- 检测输出解析与 ultralytics val 一致：conf>=0.001, NMS IoU=0.7, max_det=300, AP 为 101 点插值;
- 目标分档（COCO 口径，640x640 像素系）：小 <32^2, 中 32^2~96^2, 大 >96^2;
- 分档评估时，与其它档 GT 重叠 IoU>=0.5 的预测记为 ignore（不计 FP）;
- 噪声测试：预处理张量加 N(0, 0.02) 高斯噪声（seed=42），对比两模型 mAP50 降幅。

用法（项目根目录运行）：
  python exp3/scripts/eval_detail.py
输出：exp3/results/eval_detail.json（并在控制台打印摘要表）
"""
import glob
import json
import os

import cv2
import numpy as np
import onnxruntime as ort
import torch
import torchvision

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG_DIR = os.path.join(ROOT, "data/splits/yolo/images/test")
LBL_DIR = os.path.join(ROOT, "data/splits/yolo/labels/test")
M_FP32 = os.path.join(ROOT, "exp3/models/a2_fp32.onnx")
M_INT8 = os.path.join(ROOT, "exp3/models/a2_int8_val346.onnx")
OUT = os.path.join(ROOT, "exp3/results/eval_detail.json")

CONF, NMS_IOU, MAX_DET, IMGSZ = 0.001, 0.7, 300, 640
SMALL, LARGE = 32**2, 96**2  # COCO 面积阈值（px^2）


def load_gt(img_path):
    """YOLO 归一化 xywh -> 像素 xyxy，并按面积分档（图像统一 640x640）."""
    stem = os.path.splitext(os.path.basename(img_path))[0]
    boxes = []
    with open(os.path.join(LBL_DIR, stem + ".txt")) as f:
        for line in f:
            _, xc, yc, w, h = map(float, line.split())
            xc, yc, w, h = xc * IMGSZ, yc * IMGSZ, w * IMGSZ, h * IMGSZ
            boxes.append([xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2])
    boxes = np.array(boxes).reshape(-1, 4)
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    group = np.where(area < SMALL, 0, np.where(area <= LARGE, 1, 2))  # 0小 1中 2大
    return boxes, group


def preprocess(img_path, noise_sigma=0.0, rng=None):
    im0 = cv2.imread(img_path)
    im = cv2.resize(im0, (IMGSZ, IMGSZ)) if im0.shape[:2] != (IMGSZ, IMGSZ) else im0
    im = im[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    if noise_sigma > 0:
        im += rng.normal(0, noise_sigma, im.shape).astype(np.float32)
    return np.ascontiguousarray(im[None])


def predict(sess, inp):
    out = sess.run(None, {"images": inp})[0][0]  # (5, 8400) -> xywh + score
    out = out.T
    keep = out[:, 4] >= CONF
    out = out[keep]
    if not len(out):
        return np.zeros((0, 5), dtype=np.float32)
    xy, wh = out[:, :2], out[:, 2:4]
    boxes = np.concatenate([xy - wh / 2, xy + wh / 2], axis=1)
    idx = torchvision.ops.nms(torch.from_numpy(boxes), torch.from_numpy(out[:, 4]), NMS_IOU)[:MAX_DET]
    sel = idx.numpy()
    return np.concatenate([boxes[sel], out[sel, 4:5]], axis=1)  # xyxy + conf


def iou_matrix(a, b):
    """(n,4)x(m,4) xyxy -> (n,m) IoU."""
    lt = np.maximum(a[:, None, :2], b[None, :, :2])
    rb = np.minimum(a[:, None, 2:], b[None, :, 2:])
    wh = np.clip(rb - lt, 0, None)
    inter = wh[..., 0] * wh[..., 1]
    area_a = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1])
    area_b = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (area_a[:, None] + area_b[None, :] - inter + 1e-9)


def match_group(preds_by_img, gt_by_img, group=None):
    """贪心匹配，返回排序后的 TP 标记与 conf。group=None 表示全部 GT 参与匹配."""
    tps, confs = [], []
    for preds, (gt, groups) in zip(preds_by_img, gt_by_img):
        mask = np.ones(len(gt), bool) if group is None else groups == group
        other = np.zeros(len(gt), bool) if group is None else ~mask  # 全局模式不做跨档 ignore
        gt_g, matched = gt[mask], np.zeros(mask.sum(), bool)
        ious = iou_matrix(preds[:, :4], gt) if len(preds) and len(gt) else np.zeros((len(preds), len(gt)))
        for i, p in enumerate(preds):  # preds 已按 conf 降序（NMS 返回排序序）
            if len(gt) and other.max() and ious[i][other].max(initial=0) >= 0.5:
                continue  # 命中其它档 GT -> ignore
            if len(gt_g):
                j = ious[i][mask].argmax()
                if ious[i][mask][j] >= 0.5 and not matched[j]:
                    matched[j] = True
                    tps.append(1)
                    confs.append(p[4])
                    continue
            tps.append(0)
            confs.append(p[4])
    return np.array(tps), np.array(confs)


def ap50(tp, conf, n_gt):
    """101 点插值 AP50（与 ultralytics 口径一致）."""
    if n_gt == 0:
        return None
    order = np.argsort(-conf)
    tps = np.cumsum(tp[order])
    fps = np.cumsum(1 - tp[order])
    recall = np.concatenate(([0.0], tps / n_gt, [1.0]))
    precision = np.concatenate(([1.0], tps / (tps + fps + 1e-9), [0.0]))
    for i in range(len(precision) - 1, 0, -1):  # precision 包络（COCO 口径）
        precision[i - 1] = max(precision[i - 1], precision[i])
    return float(np.trapezoid(precision, recall))


def eval_all(preds_by_img, gt_by_img):
    tp, conf = match_group(preds_by_img, gt_by_img, None)
    res = {"map50": ap50(tp, conf, sum(len(g[0]) for g in gt_by_img))}
    for gi, name in enumerate(["small", "medium", "large"]):
        n_gt = sum((g[1] == gi).sum() for g in gt_by_img)
        tp, conf = match_group(preds_by_img, gt_by_img, gi)
        res[f"ap50_{name}"] = ap50(tp, conf, n_gt)
        res[f"n_gt_{name}"] = int(n_gt)
    return res


def per_image_ap(preds, gt):
    tp, conf = match_group([preds], [(gt, np.zeros(len(gt), int))])
    return ap50(tp, conf, len(gt)) or 0.0


def main():
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = {"fp32": ort.InferenceSession(M_FP32, so, providers=["CPUExecutionProvider"]),
            "int8": ort.InferenceSession(M_INT8, so, providers=["CPUExecutionProvider"])}
    paths = sorted(glob.glob(os.path.join(IMG_DIR, "*")))
    gt_by_img = [load_gt(p) for p in paths]
    rng = np.random.default_rng(42)

    P = {"fp32": [], "int8": [], "fp32_noise": [], "int8_noise": []}
    for i, p in enumerate(paths):
        inp = preprocess(p)
        for tag in ("fp32", "int8"):
            P[tag].append(predict(sess[tag], inp))
        if i % 50 == 0:
            print(f"[{i+1}/{len(paths)}]")
    for i, p in enumerate(paths):  # 噪声轮（同一 rng 顺序，两模型输入完全一致）
        inp = preprocess(p, 0.02, rng)
        for tag in ("fp32", "int8"):
            P[f"{tag}_noise"].append(predict(sess[tag], inp))

    out = {k: eval_all(v, gt_by_img) for k, v in P.items()}
    # 逐图 ΔAP（干净输入）
    delta = np.array([per_image_ap(a, g[0]) - per_image_ap(b, g[0])
                      for a, b, g in zip(P["fp32"], P["int8"], gt_by_img)])
    out["per_image_delta_ap"] = {
        "mean": float(delta.mean()), "std": float(delta.std()),
        "min": float(delta.min()), "max": float(delta.max()),
        "hist": np.histogram(delta, bins=10, range=(-1, 1))[0].tolist(),
        "worst_images": [paths[i] for i in np.argsort(np.abs(delta))[-5:]],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n{'':12s}{'mAP50':>8s}{'small':>8s}{'medium':>8s}{'large':>8s}")
    for k in ("fp32", "int8", "fp32_noise", "int8_noise"):
        r = out[k]
        f3 = lambda v: f"{v:8.3f}" if v is not None else f"{'--':>8s}"
        print(f"{k:12s}{f3(r['map50'])}{f3(r['ap50_small'])}{f3(r['ap50_medium'])}{f3(r['ap50_large'])}")
    print(f"GT 分布: 小 {out['fp32']['n_gt_small']} / 中 {out['fp32']['n_gt_medium']} / 大 {out['fp32']['n_gt_large']}")
    print(f"量化 ΔmAP50 = {out['int8']['map50'] - out['fp32']['map50']:+.4f}, "
          f"噪声下 fp32 {out['fp32_noise']['map50']:.3f} vs int8 {out['int8_noise']['map50']:.3f}")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
