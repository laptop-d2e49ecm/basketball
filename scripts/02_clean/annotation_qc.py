# -*- coding: utf-8 -*-
"""标注质量审计（QC）：用已训练模型当"第二标注员"交叉核对原始帧标注。

背景：2026-11-08 增强 v2 验收时发现个别原始帧标注本身失准（框在空地/漏标，源数据固有噪声）。
本工具对全部原始帧（train/val/test，共 2521 张）做三层审计，输出可疑帧清单与目检图：

1. 模型交叉核对（A1 = 仅原始帧训练、clean190 mAP50 0.9907，现成裁判）：
   - unmatched_gt：GT 框无任何 conf≥0.30 预测覆盖（IoU<0.35）→ 疑似"框在无目标处"；
   - extra_pred：conf≥0.55 预测无 GT 覆盖 → 疑似"漏标球员"；
   注意 A1 在 train 帧上训练过，存在记忆化使核对偏保守（漏报多于误报），最终以人工目检裁决。
2. 结构异常：退化框（w/h 过小或过大）、框心出界、GT 两两高重叠（重复标注）、框数异常。
3. 按视频聚合（stem 前缀 v_*_c*）：定位是否存在系统性失准的视频段。

用法：
  python scripts/02_clean/annotation_qc.py [--weights ...] [--render-top 24] [--out data/quality]
输出：annotation_audit.json / suspects_ranked.txt / renders/*.jpg（目检图，绿=匹配GT，
红=未匹配GT，橙=模型高置信预测但无GT）
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
GT_MATCH_IOU = 0.35      # GT-预测匹配线
EXTRA_PRED_CONF = 0.55   # "漏标"判定的预测置信度线
EXTRA_MATCH_IOU = 0.30
STEM_RE = re.compile(r"^(v_.+?_c\d+)")


def load_yolo(p: Path):
    return [[float(x) for x in l.split()] for l in p.read_text(encoding="utf-8").splitlines()
            if len(l.split()) == 5]


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def xywh2xyxy(r):
    cx, cy, w, h = r[1], r[2], r[3], r[4]
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def structural_flags(rows):
    flags = []
    for r in rows:
        if r[3] < 0.005 or r[4] < 0.005 or r[3] > 0.95 or r[4] > 0.95:
            flags.append("degenerate_size")
        if not (0.0 <= r[1] <= 1.0 and 0.0 <= r[2] <= 1.0):
            flags.append("center_out")
    boxes = [xywh2xyxy(r) for r in rows]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if iou(boxes[i], boxes[j]) > 0.85:
                flags.append("dup_pair")
    if len(rows) > 25:
        flags.append("too_many_boxes")
    return sorted(set(flags))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(ROOT / "models/exp2/A1_yolov8n/weights/best.pt"))
    ap.add_argument("--out", default=str(ROOT / "data/quality"))
    ap.add_argument("--render-top", type=int, default=24)
    ap.add_argument("--conf", type=float, default=0.20)
    a = ap.parse_args()
    out = Path(a.out)
    (out / "renders").mkdir(parents=True, exist_ok=True)

    model = YOLO(a.weights)
    frames = []
    for split, list_file in [("train", "original_train.txt"),
                             ("val", "original_val.txt"),
                             ("test", "original_test.txt")]:
        for line in (ROOT / "data/splits/yolo" / list_file).read_text(encoding="utf-8").splitlines():
            if line.strip():
                frames.append((split, Path(line.strip())))

    results = []
    for idx, (split, img_path) in enumerate(frames):
        lbl = ROOT / "data/splits/yolo/labels" / split / f"{img_path.stem}.txt"
        rows = load_yolo(lbl) if lbl.exists() else []
        r = model.predict(str(img_path), conf=a.conf, imgsz=640, device="cpu", verbose=False)[0]
        preds = []
        for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
            W, H = r.orig_shape[1], r.orig_shape[0]
            preds.append(((b[0] / W, b[1] / H, b[2] / W, b[3] / H), float(c)))

        gt_ious = []
        for row in rows:
            g = xywh2xyxy(row)
            gt_ious.append(max((iou(g, p) for p, c in preds if c >= 0.30), default=0.0))
        unmatched = sum(i < GT_MATCH_IOU for i in gt_ious)
        extra = sum(1 for p, c in preds
                    if c >= EXTRA_PRED_CONF and max((iou(p, xywh2xyxy(r2)) for r2 in rows), default=0.0) < EXTRA_MATCH_IOU)
        flags = structural_flags(rows)
        mean_iou = sum(gt_ious) / len(gt_ious) if gt_ious else 0.0
        score = (2.0 * unmatched / max(len(rows), 1)
                 + 0.4 * min(extra, 5) / 5
                 + (0.5 if rows and mean_iou < 0.55 else 0.0)
                 + (0.3 if flags else 0.0))
        video = STEM_RE.match(img_path.stem)
        results.append({"split": split, "stem": img_path.stem, "video": video.group(1) if video else "?",
                        "n_gt": len(rows), "unmatched_gt": unmatched, "extra_pred": extra,
                        "mean_gt_iou": round(mean_iou, 3), "flags": flags, "score": round(score, 3),
                        "path": str(img_path)})
        if (idx + 1) % 300 == 0:
            print(f"[{idx+1}/{len(frames)}] ...", flush=True)

    suspects = sorted(results, key=lambda x: -x["score"])
    by_video = defaultdict(lambda: [0, 0.0])
    for f in results:
        by_video[f["video"]][0] += 1
        by_video[f["video"]][1] += f["score"]
    video_agg = {v: {"frames": n, "mean_score": round(s / n, 3)}
                 for v, (n, s) in sorted(by_video.items(), key=lambda kv: -kv[1][1] / kv[1][0])}

    summary = {"frames_total": len(results),
               "frames_score_ge_1.0": sum(f["score"] >= 1.0 for f in results),
               "frames_score_ge_0.7": sum(f["score"] >= 0.7 for f in results),
               "frames_with_flags": sum(bool(f["flags"]) for f in results),
               "gt_boxes_total": sum(f["n_gt"] for f in results),
               "unmatched_gt_total": sum(f["unmatched_gt"] for f in results),
               "extra_pred_total": sum(f["extra_pred"] for f in results)}
    (out / "annotation_audit.json").write_text(
        json.dumps({"summary": summary, "video_aggregation": video_agg,
                    "top100": suspects[:100]}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "suspects_ranked.txt").write_text(
        "\n".join(f'{f["score"]:.3f}\t{f["split"]}\t{f["stem"]}\t'
                  f'gt={f["n_gt"]} unmatched={f["unmatched_gt"]} extra={f["extra_pred"]} '
                  f'meanIoU={f["mean_gt_iou"]} {",".join(f["flags"])}' for f in suspects[:100]),
        encoding="utf-8")

    # ---- 目检图：每 4 帧一张 2x2 拼图（红=未匹配GT，绿=匹配GT，橙=高置信预测无GT） ----
    for g in range(0, min(a.render_top, len(suspects)), 4):
        batch = suspects[g:g + 4]
        tiles = []
        for f in batch:
            img = Image.open(f["path"]).convert("RGB").resize((640, 640))
            d = ImageDraw.Draw(img)
            lbl = ROOT / "data/splits/yolo/labels" / f["split"] / (f["stem"] + ".txt")
            rows = load_yolo(lbl)
            r = model.predict(f["path"], conf=a.conf, imgsz=640, device="cpu", verbose=False)[0]
            ow, oh = r.orig_shape[1], r.orig_shape[0]
            gt_boxes = [xywh2xyxy(x) for x in rows]
            pred_boxes = [(((b[0] / ow, b[1] / oh, b[2] / ow, b[3] / oh)), float(c))
                          for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
            for gb in gt_boxes:
                best = max((iou(gb, p) for p, c in pred_boxes if c >= 0.30), default=0.0)
                bad = best < GT_MATCH_IOU
                d.rectangle([gb[0] * 640, gb[1] * 640, gb[2] * 640, gb[3] * 640],
                            outline=(255, 40, 40) if bad else (40, 200, 40), width=4 if bad else 2)
            for p, c in pred_boxes:
                if c >= EXTRA_PRED_CONF and max((iou(p, gb) for gb in gt_boxes), default=0.0) < EXTRA_MATCH_IOU:
                    d.rectangle([p[0] * 640, p[1] * 640, p[2] * 640, p[3] * 640],
                                outline=(255, 160, 0), width=3)
            d.text((8, 6), f["stem"][:38] + f'  score={f["score"]}', fill=(255, 255, 0))
            tiles.append(img)
        while len(tiles) < 4:
            tiles.append(Image.new("RGB", (640, 640), (0, 0, 0)))
        sheet = Image.new("RGB", (1288, 1288), (255, 255, 255))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % 2) * 644 + 2, (i // 2) * 644 + 2))
        sheet.save(out / "renders" / f"sheet_{g//4:02d}_rank{g+1}-{g+len(batch)}.jpg", quality=88)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[OK] top suspects -> {out/'suspects_ranked.txt'} ; renders -> {out/'renders'}")


if __name__ == "__main__":
    main()
