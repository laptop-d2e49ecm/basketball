# -*- coding: utf-8 -*-
"""实验2 v2 重训模型 · 本地终评（test 190 原始帧，与 A1 旧成绩同一把尺子）。

权重摆放约定（从 Kaggle 下载后）：
    models/exp2_v2/A1_yolov8n/weights/best.pt   （+ last.pt / args.yaml / results.csv）
    models/exp2_v2/A2_yolov8n/weights/best.pt
    models/exp2_v2/A2_yolov8m/weights/best.pt
（Kaggle 输出目录名 A2_yolov8 / 配置 A2_magic.yaml 无需对应，放对本地目录即可）

用法（仓库根目录）：
    .venv/Scripts/python.exe models/exp2_v2/eval_test190.py                 # 评 exp2_v2 下全部已有模型
    .venv/Scripts/python.exe models/exp2_v2/eval_test190.py --with-old      # 附带旧版 A1/A2/M1 对照
    .venv/Scripts/python.exe models/exp2_v2/eval_test190.py \
        --weights models/exp2/A1_yolov8n/weights/best.pt --name A1-repro    # 评任意单个权重

口径：data_clean.yaml test split（190 张原始帧，1792 框）；conf=0.001、NMS IoU=0.7、
max_det=100、imgsz=640、CPU——与实验3 复核、P2 测速报告完全一致。
输出：终端对比表 + models/exp2_v2/eval_test190.json
"""
import argparse
import json
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
V2_DIR = ROOT / "models/exp2_v2"
OLD = {"A1(旧)": "A1_yolov8n", "A2(旧)": "A2_yolov8n", "M1(旧)": "A2_yolov8m"}
REF = {  # 旧版干净口径已实测成绩（exp3 复核），供直接对照
    "A1(旧)": {"map50": 0.9907, "map50_95": 0.7546},
    "A2(旧)": {"map50": 0.987, "map50_95": 0.734},
    "M1(旧)": {"map50": 0.990, "map50_95": 0.767},
}


def evaluate(name: str, weights: str):
    r = YOLO(weights).val(
        data=str(ROOT / "data/splits/yolo/data_clean.yaml"), split="test",
        imgsz=640, batch=16, device="cpu",
        conf=0.001, iou=0.7, max_det=100, verbose=False, plots=False)
    return {"name": name, "map50": round(float(r.box.map50), 4),
            "map50_95": round(float(r.box.map), 4),
            "P": round(float(r.box.mp), 4), "R": round(float(r.box.mr), 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-old", action="store_true", help="附带旧版 A1/A2/M1 复测")
    ap.add_argument("--weights", action="append", default=[], help="额外权重路径（可多次）")
    ap.add_argument("--name", action="append", default=[], help="与 --weights 对应的显示名")
    a = ap.parse_args()

    jobs = []
    for run_dir in sorted(V2_DIR.glob("*/weights/best.pt")):
        jobs.append((run_dir.parents[1].name, str(run_dir)))
    if a.with_old:
        for label, d in OLD.items():
            p = ROOT / "models/exp2" / d / "weights/best.pt"
            if p.exists():
                jobs.append((label, str(p)))
    for i, w in enumerate(a.weights):
        jobs.append((a.name[i] if i < len(a.name) else Path(w).stem, w))

    if not jobs:
        print("models/exp2_v2/ 下还没有 best.pt —— 先把 Kaggle 产物按目录约定放好，"
              "或用 --weights 指定路径。")
        return

    results = []
    for name, w in jobs:
        print(f"[eval] {name} <- {w}", flush=True)
        results.append(evaluate(name, w))

    print("\n| 模型 | P | R | mAP50 | mAP50-95 |")
    print("|---|---|---|---|---|")
    for x in results:
        ref = REF.get(x["name"])
        tail = f"（旧版实测 {ref['map50']}/{ref['map50_95']}）" if ref else ""
        print(f'| {x["name"]} | {x["P"]:.4f} | {x["R"]:.4f} | '
              f'{x["map50"]:.4f} | {x["map50_95"]:.4f} |{tail}')
    out = V2_DIR / "eval_test190.json"
    out.write_text(json.dumps({"scope": "test190 originals, data_clean.yaml",
                               "results": results}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"\n[OK] 已写入 {out}")


if __name__ == "__main__":
    main()
