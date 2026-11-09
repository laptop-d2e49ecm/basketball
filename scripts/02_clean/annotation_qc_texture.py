# -*- coding: utf-8 -*-
"""标注质量审计第二关（训练自由判据，免疫模型记忆化）：

背景：第一关（annotation_qc.py，A1 当第二标注员）在 train 帧上因模型记忆化而失明
（已知坏帧 v_2j7kLB-vEEk_c001__f000450 未命中）。本关改用两个不依赖任何训练模型的信号：

A. 框内纹理 vs 同图背景纹理：真球员框内是人体（高频纹理），"框在空地/看台"的框
   内部纹理与背景无差别。对每个 GT 框计算内部梯度幅值统计，与同图随机背景块
   （不与任何 GT 框重叠）的分布比较，低差异 = 可疑背景框；
B. 时序框数一致性：同一视频相邻帧（帧号差 ≤60）球员数应平滑，孤立跳变帧可疑。

用法：python scripts/02_clean/annotation_qc_texture.py [--render-top 24] [--out data/quality]
输出：texture_audit.json / texture_suspects_ranked.txt / renders_tex/*.jpg
锚定验收：已知坏帧 f000450（约半数框在空地）必须进入排名头部，否则本关判据无效。
"""
import argparse
import json
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
FIDX_RE = re.compile(r"__f(\d+)$")
VIDEO_RE = re.compile(r"^(v_.+?_c\d+)")
TEMP_NEIGH = 60          # 时序邻域最大帧号差
COUNT_JUMP = 4           # 框数跳变阈值
BG_PATCHES = 24          # 每图随机背景块数
Z_SUSPECT = 0.35         # 框纹理相对背景分布的可疑分位（越低越像背景）


def load_yolo(p: Path):
    return [[float(x) for x in l.split()] for l in p.read_text(encoding="utf-8").splitlines()
            if len(l.split()) == 5]


def grad_mag(gray: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(gray)
    return np.hypot(gx, gy)


def box_texture(gm: np.ndarray, x1, y1, x2, y2, shrink=0.12):
    h, w = gm.shape
    bw, bh = (x2 - x1) * w, (y2 - y1) * h
    ix1, iy1 = int((x1 + bw * shrink / w) * w), int((y1 + bh * shrink / h) * h)
    ix2, iy2 = int((x2 - bw * shrink / w) * w), int((y2 - bh * shrink / h) * h)
    ix1, iy1, ix2, iy2 = max(ix1, 0), max(iy1, 0), min(ix2, w), min(iy2, h)
    if ix2 - ix1 < 4 or iy2 - iy1 < 4:
        return None
    patch = gm[iy1:iy2, ix1:ix2]
    return float(patch.mean())


def overlaps_any(cx1, cy1, cx2, cy2, boxes, margin=0.02):
    for (bx1, by1, bx2, by2) in boxes:
        ix1, iy1 = max(cx1, bx1 - margin), max(cy1, by1 - margin)
        ix2, iy2 = min(cx2, bx2 + margin), min(cy2, by2 + margin)
        if ix2 - ix1 > 0 and iy2 - iy1 > 0:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/quality"))
    ap.add_argument("--render-top", type=int, default=24)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    out = Path(a.out)
    (out / "renders_tex").mkdir(parents=True, exist_ok=True)
    random.seed(a.seed)

    frames = []
    for split, list_file in [("train", "original_train.txt"),
                             ("val", "original_val.txt"),
                             ("test", "original_test.txt")]:
        for line in (ROOT / "data/splits/yolo" / list_file).read_text(encoding="utf-8").splitlines():
            if line.strip():
                frames.append((split, Path(line.strip())))

    # ---- A. 纹理关 ----
    rows_all = []
    for split, img_path in frames:
        lbl = ROOT / "data/splits/yolo/labels" / split / f"{img_path.stem}.txt"
        rows = load_yolo(lbl) if lbl.exists() else []
        if not rows:
            continue
        img = Image.open(img_path).convert("L")
        W, H = img.size
        gm = grad_mag(np.asarray(img, dtype=np.float32))
        boxes = [(r[1] - r[3] / 2, r[2] - r[4] / 2, r[1] + r[3] / 2, r[2] + r[4] / 2) for r in rows]
        # 背景块：随机放置，尺寸取框尺寸中位数，避开所有 GT
        med_w = statistics.median(b[2] - b[0] for b in boxes)
        med_h = statistics.median(b[3] - b[1] for b in boxes)
        bg_vals = []
        for _ in range(BG_PATCHES * 4):
            if len(bg_vals) >= BG_PATCHES:
                break
            cx = random.uniform(0, 1 - med_w)
            cy = random.uniform(0, 1 - med_h)
            c = (cx, cy, cx + med_w, cy + med_h)
            if overlaps_any(*c, boxes):
                continue
            v = box_texture(gm, *c)
            if v is not None:
                bg_vals.append(v)
        if len(bg_vals) < 6:
            continue
        bg_mu, bg_sd = statistics.fmean(bg_vals), statistics.pstdev(bg_vals) + 1e-6
        low_boxes = []
        bg_sorted = sorted(bg_vals)
        low_boxes = []
        box_z = []
        for b in boxes:
            v = box_texture(gm, *b)
            if v is None:
                continue
            # 框纹理低于多少比例的背景块 → 背景相似度
            frac_below = sum(1 for x in bg_sorted if x <= v) / len(bg_sorted)
            box_z.append(frac_below)
            if frac_below <= Z_SUSPECT:
                low_boxes.append(b)
        score = len(low_boxes) / max(len(boxes), 1)
        m = VIDEO_RE.match(img_path.stem)
        fidx = FIDX_RE.search(img_path.stem)
        rows_all.append({"split": split, "stem": img_path.stem,
                         "video": m.group(1) if m else "?",
                         "fidx": int(fidx.group(1)) if fidx else -1,
                         "n_gt": len(boxes), "n_lowtex": len(low_boxes),
                         "lowtex_frac": round(score, 3), "path": str(img_path),
                         "low_boxes": low_boxes})
        if len(rows_all) % 400 == 0:
            print(f"[{len(rows_all)}/{len(frames)}] ...", flush=True)

    # ---- B. 时序框数关 ----
    by_video = defaultdict(list)
    for f in rows_all:
        by_video[f["video"]].append(f)
    for v, fl in by_video.items():
        fl.sort(key=lambda x: x["fidx"])
        for i, f in enumerate(fl):
            neigh = [g["n_gt"] for g in fl
                     if g is not f and abs(g["fidx"] - f["fidx"]) <= TEMP_NEIGH]
            if len(neigh) >= 2:
                med = statistics.median(neigh)
                if abs(f["n_gt"] - med) >= COUNT_JUMP:
                    f["count_jump"] = f["n_gt"] - med

    suspects = sorted(rows_all, key=lambda x: -x["lowtex_frac"])
    summary = {"frames": len(rows_all),
               "frames_lowtex_ge_0.3": sum(f["lowtex_frac"] >= 0.3 for f in rows_all),
               "frames_lowtex_ge_0.2": sum(f["lowtex_frac"] >= 0.2 for f in rows_all),
               "frames_count_jump": sum("count_jump" in f for f in rows_all),
               "boxes_total": sum(f["n_gt"] for f in rows_all),
               "boxes_lowtex": sum(f["n_lowtex"] for f in rows_all)}
    anchor_rank = next((i + 1 for i, f in enumerate(suspects)
                        if f["stem"] == "v_2j7kLB-vEEk_c001__f000450"), None)
    summary["anchor_f000450_rank"] = anchor_rank

    (out / "texture_audit.json").write_text(
        json.dumps({"summary": summary, "top150": [
            {k: v for k, v in f.items() if k != "low_boxes"} for f in suspects[:150]]},
            ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "texture_suspects_ranked.txt").write_text(
        "\n".join(f'{f["lowtex_frac"]:.3f}\t{f["split"]}\t{f["stem"]}\t'
                  f'gt={f["n_gt"]} lowtex={f["n_lowtex"]} '
                  f'{"count_jump=" + str(f["count_jump"]) if "count_jump" in f else ""}'
                  for f in suspects[:150]), encoding="utf-8")

    # ---- 目检图 ----
    for g in range(0, min(a.render_top, len(suspects)), 4):
        batch = suspects[g:g + 4]
        tiles = []
        for f in batch:
            img = Image.open(f["path"]).convert("RGB").resize((640, 640))
            d = ImageDraw.Draw(img)
            low = set(map(tuple, f["low_boxes"]))
            lbl = ROOT / "data/splits/yolo/labels" / f["split"] / (f["stem"] + ".txt")
            for r in load_yolo(lbl):
                b = (r[1] - r[3] / 2, r[2] - r[4] / 2, r[1] + r[3] / 2, r[2] + r[4] / 2)
                bad = tuple(b) in low
                d.rectangle([b[0] * 640, b[1] * 640, b[2] * 640, b[3] * 640],
                            outline=(255, 40, 40) if bad else (40, 200, 40),
                            width=4 if bad else 2)
            tag = f["stem"][:38] + f'  lowtex={f["lowtex_frac"]}'
            if "count_jump" in f:
                tag += f'  jump={f["count_jump"]:+d}'
            d.text((8, 6), tag, fill=(255, 255, 0))
            tiles.append(img)
        while len(tiles) < 4:
            tiles.append(Image.new("RGB", (640, 640), (0, 0, 0)))
        sheet = Image.new("RGB", (1288, 1288), (255, 255, 255))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % 2) * 644 + 2, (i // 2) * 644 + 2))
        sheet.save(out / "renders_tex" / f"sheet_{g//4:02d}_rank{g+1}-{g+len(batch)}.jpg", quality=88)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[OK] ranked -> {out/'texture_suspects_ranked.txt'} ; renders -> {out/'renders_tex'}")


if __name__ == "__main__":
    main()
