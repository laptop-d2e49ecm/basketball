# -*- coding: utf-8 -*-
"""实验3 v2：量化误差细粒度分析（分层 AP / 逐图 ΔAP / 噪声鲁棒性）。

复用 v1 自研评估器（models/exp3/scripts/eval_detail.py 的纯函数，口径不变：
conf>=0.001, NMS IoU=0.7, max_det=300, 101 点插值 AP, COCO 面积分档），
仅切换到 v2 模型与 test190 原始帧。

对比对象：A2′ FP32 ONNX vs A2′ INT8 E1(val173)，同一 ONNX Runtime CPU 引擎。
用法：.venv/Scripts/python.exe models/exp3_v2/eval_detail_v2.py
输出：models/exp3_v2/eval_detail_v2.json
"""
import glob
import json
import os
import sys

import numpy as np
import onnxruntime as ort

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # models/exp3_v2/x.py -> 仓库根
sys.path.insert(0, os.path.join(ROOT, "models/exp3/scripts"))
import eval_detail as ed  # noqa: E402  v1 自研评估器（纯函数复用，路径全局量在下方覆写）

IMG_DIR = os.path.join(ROOT, "data/splits/yolo/images/test")
LBL_DIR = os.path.join(ROOT, "data/splits/yolo/labels/test")
M_FP32 = os.path.join(ROOT, "models/exp3_v2/models/a2v2_fp32.onnx")
M_INT8 = os.path.join(ROOT, "models/exp3_v2/models/a2v2_int8_val173.onnx")
OUT = os.path.join(ROOT, "models/exp3_v2/eval_detail_v2.json")

ed.LBL_DIR = LBL_DIR  # load_gt 内部引用的全局量指到正确目录


def main():
    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = {"fp32": ort.InferenceSession(M_FP32, so, providers=["CPUExecutionProvider"]),
            "int8": ort.InferenceSession(M_INT8, so, providers=["CPUExecutionProvider"])}
    paths = sorted(glob.glob(os.path.join(IMG_DIR, "*")))
    print(f"[scope] {len(paths)} test images")
    gt_by_img = [ed.load_gt(p) for p in paths]
    rng = np.random.default_rng(42)

    P = {"fp32": [], "int8": [], "fp32_noise": [], "int8_noise": []}
    for i, p in enumerate(paths):
        inp = ed.preprocess(p)
        for tag in ("fp32", "int8"):
            P[tag].append(ed.predict(sess[tag], inp))
        if i % 50 == 0:
            print(f"[{i+1}/{len(paths)}]", flush=True)
    for i, p in enumerate(paths):
        inp = ed.preprocess(p, 0.02, rng)
        for tag in ("fp32", "int8"):
            P[f"{tag}_noise"].append(ed.predict(sess[tag], inp))

    out = {k: ed.eval_all(v, gt_by_img) for k, v in P.items()}
    # Δ = AP(INT8) − AP(FP32)：负值 = 量化使该图变差（v1 main() 为 FP32−INT8，与图注符号相反）
    delta = np.array([ed.per_image_ap(b, g[0]) - ed.per_image_ap(a, g[0])
                      for a, b, g in zip(P["fp32"], P["int8"], gt_by_img)])
    order = np.argsort(delta)
    out["per_image_delta_ap"] = {
        "definition": "AP50(INT8) - AP50(FP32) per image",
        "mean": float(delta.mean()), "std": float(delta.std()),
        "min": float(delta.min()), "max": float(delta.max()),
        "n_images": int(len(delta)),
        "n_unchanged": int((np.abs(delta) < 1e-9).sum()),
        "n_within_0.05": int((np.abs(delta) <= 0.05).sum()),
        "values": [round(float(v), 5) for v in delta],
        "worst_images": [{"image": os.path.basename(paths[i]), "delta": round(float(delta[i]), 4)}
                         for i in order[:5]],
        "best_images": [{"image": os.path.basename(paths[i]), "delta": round(float(delta[i]), 4)}
                        for i in order[::-1][:5]],
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
          f"噪声下 fp32 {out['fp32_noise']['map50']:.4f} vs int8 {out['int8_noise']['map50']:.4f}")
    d = out["per_image_delta_ap"]
    print(f"逐图ΔAP(INT8−FP32): mean={d['mean']:+.4f} std={d['std']:.4f} min={d['min']:+.4f} max={d['max']:+.4f} "
          f"不变 {d['n_unchanged']}/{d['n_images']}，|Δ|≤0.05 {d['n_within_0.05']}/{d['n_images']}")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
