# -*- coding: utf-8 -*-
"""标注质量审计第三关（COCO 盲裁判）：yolov8n COCO 预训练权重检测"人"，交叉核对全部 GT。

为什么需要第三关：
- 第一关（A1 当裁判）在 train 帧上被记忆化弄瞎（已知坏帧 f000450 未命中）；
- 第二关（纹理 vs 背景）锚定验收失败（球馆观众席纹理高于球员，判据无效，已弃用）；
- COCO 预训练模型从未见过本项目标注 → 完全无记忆化，"标注的球员框上没有 COCO 检出的人"
  是"框在无人处"的强信号。

主判据（单向、干净）：unmatched_gt = GT 框无任何 COCO person（conf≥0.25，IoU≥0.30）覆盖。
辅判据（含裁判/教练/观众噪声，仅报告不计分）：extra_person = COCO person 无 GT 覆盖。

锚定验收：已知坏帧 v_2j7kLB-vEEk_c001__f000450（约半数框在空地）必须进排名头部。
用法：python scripts/02_clean/annotation_qc_coco.py [--render-top 24]
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]
GT_MATCH_IOU = 0.30
PRED_CONF = 0.25


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default=str(ROOT / "yolov8n.pt"))
    ap.add_argument("--out", default=str(ROOT / "data/quality"))
    ap.add_argument("--render-top", type=int, default=24)
    a = ap.parse_args()
    out = Path(a.out)
    (out / "renders_coco").mkdir(parents=True, exist_ok=True)

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
        r = model.predict(str(img_path), conf=PRED_CONF, imgsz=640, classes=[0],
                          device="cpu", verbose=False)[0]
        ow, oh = r.orig_shape[1], r.orig_shape[0]
        persons = [((b[0] / ow, b[1] / oh, b[2] / ow, b[3] / oh), float(c))
                   for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]
        gt_boxes = [xywh2xyxy(x) for x in rows]
        unmatched = sum(1 for g in gt_boxes
                        if max((iou(g, p) for p, c in persons), default=0.0) < GT_MATCH_IOU)
        extra = sum(1 for p, c in persons
                    if max((iou(p, g) for g in gt_boxes), default=0.0) < GT_MATCH_IOU)
        frac = unmatched / max(len(gt_boxes), 1)
        results.append({"split": split, "stem": img_path.stem, "path": str(img_path),
                        "n_gt": len(gt_boxes), "unmatched": unmatched,
                        "extra_person": extra, "frac": round(frac, 3),
                        "score": round(frac + 0.05 * min(extra, 4), 3)})
        if (idx + 1) % 400 == 0:
            print(f"[{idx+1}/{len(frames)}] ...", flush=True)

    suspects = sorted(results, key=lambda x: -x["score"])
    anchor_rank = next((i + 1 for i, f in enumerate(suspects)
                        if f["stem"] == "v_2j7kLB-vEEk_c001__f000450"), None)
    summary = {"frames": len(results),
               "anchor_f000450_rank": anchor_rank,
               "frames_unmatched_ge_2": sum(f["unmatched"] >= 2 for f in results),
               "frames_frac_ge_0.3": sum(f["frac"] >= 0.3 for f in results),
               "gt_total": sum(f["n_gt"] for f in results),
               "gt_unmatched_total": sum(f["unmatched"] for f in results),
               "extra_person_total": sum(f["extra_person"] for f in results)}
    (out / "coco_audit.json").write_text(
        json.dumps({"summary": summary, "top150": suspects[:150]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "coco_suspects_ranked.txt").write_text(
        "\n".join(f'{f["score"]:.3f}\t{f["split"]}\t{f["stem"]}\t'
                  f'gt={f["n_gt"]} unmatched={f["unmatched"]} extra_person={f["extra_person"]}'
                  for f in suspects[:150]), encoding="utf-8")

    for g in range(0, min(a.render_top, len(suspects)), 4):
        batch = suspects[g:g + 4]
        tiles = []
        for f in batch:
            img = Image.open(f["path"]).convert("RGB").resize((640, 640))
            d = ImageDraw.Draw(img)
            rows = load_yolo(ROOT / "data/splits/yolo/labels" / f["split"] / (f["stem"] + ".txt"))
            r = model.predict(f["path"], conf=PRED_CONF, imgsz=640, classes=[0],
                              device="cpu", verbose=False)[0]
            ow, oh = r.orig_shape[1], r.orig_shape[0]
            for row in rows:
                gb = xywh2xyxy(row)
                best = max((iou(gb, (b[0] / ow, b[1] / oh, b[2] / ow, b[3] / oh))
                            for b in r.boxes.xyxy.tolist()), default=0.0)
                bad = best < GT_MATCH_IOU
                d.rectangle([gb[0] * 640, gb[1] * 640, gb[2] * 640, gb[3] * 640],
                            outline=(255, 40, 40) if bad else (40, 200, 40), width=4 if bad else 2)
            d.text((8, 6), f["stem"][:38] + f'  unmatched={f["unmatched"]}/{f["n_gt"]}',
                   fill=(255, 255, 0))
            tiles.append(img)
        while len(tiles) < 4:
            tiles.append(Image.new("RGB", (640, 640), (0, 0, 0)))
        sheet = Image.new("RGB", (1288, 1288), (255, 255, 255))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % 2) * 644 + 2, (i // 2) * 644 + 2))
        sheet.save(out / "renders_coco" / f"sheet_{g//4:02d}_rank{g+1}-{g+len(batch)}.jpg", quality=88)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[OK] ranked -> {out/'coco_suspects_ranked.txt'} ; renders -> {out/'renders_coco'}")


if __name__ == "__main__":
    main()
