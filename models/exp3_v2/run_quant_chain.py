# -*- coding: utf-8 -*-
"""实验3 v2 精度线量化链（底座 A2′，教师 M1′，全本地 CPU）。

步骤：
1. A2′ best.pt → ONNX FP32（ultralytics 导出，口径同 v1）；
2. INT8 静态量化三组校准实验：E1 val173 / E2 train500 / E4 per-channel(val173)
   （复用 models/exp3/scripts/export_quant.py，量化范围与 v1 一致：仅 Conv/Gemm/MatMul）；
3. 叠加实验：最优学生 dis6 → ONNX → E1 同口径 INT8；
4. 全部模型 test 190 终评（与 exp2_v2/eval_test190.py 同口径），写 quant_chain_v2.json。
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "models/exp3_v2/models"
OUT.mkdir(parents=True, exist_ok=True)
A2V2 = ROOT / "models/exp2_v2/A2_yolov8n/weights/best.pt"
DIS6 = ROOT / "models/exp3_v2/exp3-v3/a2v2_distill_dis6_best.pt"
QUANT = ROOT / "models/exp3/scripts/export_quant.py"
PY = sys.executable


def sh(*cmd):
    print(">>", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=str(ROOT))


def export_onnx(weights: Path, out_name: str) -> Path:
    YOLO(str(weights)).export(format="onnx", imgsz=640)
    src = weights.parent / (weights.stem + ".onnx")
    dst = OUT / out_name
    shutil.move(str(src), str(dst))
    print(f"[export] {dst.name} = {dst.stat().st_size/1e6:.1f} MB", flush=True)
    return dst


def evaluate(name: str, path: Path) -> dict:
    r = YOLO(str(path)).val(
        data=str(ROOT / "data/splits/yolo/data_clean.yaml"), split="test",
        imgsz=640, batch=16, device="cpu",
        conf=0.001, iou=0.7, max_det=100, verbose=False, plots=False)
    return {"name": name, "path": str(path.relative_to(ROOT)),
            "size_MB": round(path.stat().st_size / 1e6, 1),
            "map50": round(float(r.box.map50), 4),
            "map50_95": round(float(r.box.map), 4),
            "P": round(float(r.box.mp), 4), "R": round(float(r.box.mr), 4)}


def main():
    results = []
    # 1-2. A2′ 主线
    fp32 = export_onnx(A2V2, "a2v2_fp32.onnx")
    e1 = OUT / "a2v2_int8_val173.onnx"
    e2 = OUT / "a2v2_int8_train500.onnx"
    e4 = OUT / "a2v2_int8_val173_pc.onnx"
    sh(PY, QUANT, "--src", fp32, "--out", e1, "--split", "val", "--n", 173)
    sh(PY, QUANT, "--src", fp32, "--out", e2, "--split", "train", "--n", 500)
    sh(PY, QUANT, "--src", fp32, "--out", e4, "--split", "val", "--n", 173, "--per-channel")
    # 3. 叠加：dis6 学生
    dis6_fp32 = export_onnx(DIS6, "dis6v2_fp32.onnx")
    dis6_int8 = OUT / "dis6v2_int8_val173.onnx"
    sh(PY, QUANT, "--src", dis6_fp32, "--out", dis6_int8, "--split", "val", "--n", 173)

    # 4. 终评
    for name, p in [("A2′ ONNX FP32", fp32), ("A2′ INT8 E1(val173)", e1),
                    ("A2′ INT8 E2(train500)", e2), ("A2′ INT8 E4(per-ch)", e4),
                    ("dis6 ONNX FP32", dis6_fp32), ("dis6+INT8 叠加", dis6_int8)]:
        print(f"[eval] {name}", flush=True)
        results.append(evaluate(name, p))
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)

    ref = json.load(open(ROOT / "models/exp2_v2/eval_test190.json", encoding="utf-8"))
    out = {"scope": "test190 originals", "exp2_v2_reference": ref["results"], "quant_chain": results}
    (ROOT / "models/exp3_v2/quant_chain_v2.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n| 模型 | 体积MB | mAP50 | mAP50-95 | P | R |")
    print("|---|---|---|---|---|---|")
    for x in results:
        print(f'| {x["name"]} | {x["size_MB"]} | {x["map50"]:.4f} | '
              f'{x["map50_95"]:.4f} | {x["P"]:.4f} | {x["R"]:.4f} |')
    print("[OK] models/exp3_v2/quant_chain_v2.json")


if __name__ == "__main__":
    main()
