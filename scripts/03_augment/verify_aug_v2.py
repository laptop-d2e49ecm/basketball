# -*- coding: utf-8 -*-
"""任务 1.2.2 修复后校验工具（v2 常设关卡）：证明 _aug0 副本"图像真的变了、框跟着几何走"。

背景：旧版因 torchvision v2 传 numpy 导致图像不变、仅框被随机平移（2026-10 事故，
证据见 data/archive/exp1_aug0_broken/）。本脚本是修复后的强制验收步骤，增强产出必须先过本关再入库。

三项检查：
1. 像素级（缺陷签名，全量参与几何判定+抽样报告）：副本与原图逐像素差必须 > 0.5 —— 缺陷版恒为 0.0；
2. 仿射对齐一致性（核心判据，抽样）：对每个副本搜索 (缩放 s∈[0.86,1.14], 平移 dx/dy)，
   用 NCC 选最优仿射参数将【原图】对齐到【副本】，再把原始标注框经同一仿射映射后与副本框算 IoU
   —— 若框跟着图走，对齐后框-框 IoU 应接近 1；缺陷版框随机错位、无单一仿射可解释，必挂；
3. 代码级佐证：合成图单测（已知矩形过 augment_v2()，框-矩形 IoU ≥ 0.93，见执行记录）。

用法：
  python scripts/03_augment/verify_aug_v2.py --dir data/retrain_aug [--n-pixel 40] [--n-affine 300]

判定通过线：像素差全部 >0.5；对齐后中位框 IoU ≥0.85 且 ≥90% 的框 IoU ≥0.7。
"""
import argparse
import json
import random
import statistics
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SMALL = 320
SCALES = [round(0.86 + 0.01 * i, 2) for i in range(29)]  # 0.86–1.14 覆盖 scale(0.9,1.1)+估计余量


def load_yolo(p: Path):
    return [[float(x) for x in l.split()] for l in p.read_text(encoding="utf-8").splitlines()
            if len(l.split()) == 5]


def gray_small(img: Image.Image, size: int = SMALL) -> np.ndarray:
    return np.asarray(img.convert("L").resize((size, size)), dtype=np.float32)


def to_xyxy(r):
    cx, cy, w, h = r[1], r[2], r[3], r[4]
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def shifted_peak(ref: np.ndarray, aug: np.ndarray):
    """相位相关：返回 aug 相对 ref 的平移(整数,SMALL尺度)及峰响应。内容位移 = -返回值。"""
    A = np.fft.rfft2(ref - ref.mean())
    B = np.fft.rfft2(aug - aug.mean())
    R = A * np.conj(B)
    R /= (np.abs(R) + 1e-9)
    r = np.fft.irfft2(R, s=ref.shape)
    pk = np.unravel_index(np.argmax(r), r.shape)
    dy, dx = int(pk[0]), int(pk[1])
    if dy > ref.shape[0] // 2:
        dy -= ref.shape[0]
    if dx > ref.shape[1] // 2:
        dx -= ref.shape[1]
    return dx, dy, float(r.max())


def zoom_about_center(img: Image.Image, s: float, size: int = SMALL) -> Image.Image:
    z = img.resize((max(1, round(size * s)), max(1, round(size * s))))
    canvas = Image.new("L", (size, size))
    off = ((size - z.width) // 2, (size - z.height) // 2)
    canvas.paste(z, off)
    return canvas


def best_affine(ref_img: Image.Image, aug_arr: np.ndarray):
    """搜索 (s, Dx, Dy) 使缩放平移后的 ref 与 aug 的 NCC 最大。
    返回的 (Dx, Dy) 是 aug 相对 ref 的【内容位移】（= 相位相关峰的相反数），SMALL 尺度。"""
    a = aug_arr - aug_arr.mean()
    a_norm = np.linalg.norm(a)
    best = (1.0, 0, 0, -1.0)
    for s in SCALES:
        rs = np.asarray(zoom_about_center(ref_img, s), dtype=np.float32)
        px, py, _ = shifted_peak(rs, aug_arr)  # 峰 = -(内容位移)
        dx, dy = -px, -py
        rolled = np.roll(np.roll(rs, dy, axis=0), dx, axis=1)
        r = rolled - rolled.mean()
        denom = np.linalg.norm(r) * a_norm
        if denom < 1e-6:
            continue
        ncc = float((r * a).sum() / denom)
        if ncc > best[3]:
            best = (s, dx, dy, ncc)
    return best


def draw_boxes(img: Image.Image, rows, color, width):
    d = ImageDraw.Draw(img)
    W, H = img.size
    for r in rows:
        x1, y1, x2, y2 = to_xyxy(r)
        d.rectangle([x1 * W, y1 * H, x2 * W, y2 * H], outline=color, width=width)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/retrain_aug")
    ap.add_argument("--n-pixel", type=int, default=40, help="像素级抽查对数")
    ap.add_argument("--n-affine", type=int, default=300, help="仿射对齐校验抽样对数")
    ap.add_argument("--render", type=int, default=3)
    ap.add_argument("--render-out", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    root = Path(a.dir)
    img_dir, lbl_dir = root / "images", root / "labels"
    origs = sorted(p for p in img_dir.glob("*.jpg") if "_aug" not in p.stem)
    random.seed(a.seed)
    stems = [p.stem for p in origs]

    # ---- 自检：已知 (s, Dx, Dy) 合成扭曲必须被完整恢复 ----
    p0 = origs[0]
    img0 = Image.open(p0)
    g0 = gray_small(img0)
    s0, Dx0, Dy0 = 1.07, 9, -6
    z0 = np.asarray(zoom_about_center(img0.convert("L").resize((SMALL, SMALL)), s0), dtype=np.float32)
    warped0 = np.roll(np.roll(z0, Dy0, axis=0), Dx0, axis=1)
    s_hat, dx_hat, dy_hat, ncc0 = best_affine(img0.convert("L").resize((SMALL, SMALL)), warped0)
    assert abs(s_hat - s0) <= 0.02 and abs(dx_hat - Dx0) <= 1 and abs(dy_hat - Dy0) <= 1, \
        f"仿射恢复自检失败: true=({s0},{Dx0},{Dy0}) got=({s_hat},{dx_hat},{dy_hat})"
    print(f"[selftest] synthetic warp recovered: s={s_hat} D=({dx_hat},{dy_hat}) ncc={ncc0:.3f}")

    pixel_set = set(random.sample(stems, min(a.n_pixel, len(stems))))
    affine_set = set(random.sample(stems, min(a.n_affine, len(stems))))

    n_flip = 0
    pixel_diffs = []
    aligned_ious = []
    worst = []  # (median_iou, stem, geo, s, ncc)
    for p in origs:
        aug_p = img_dir / f"{p.stem}_aug0.jpg"
        if not aug_p.exists():
            continue
        o, g = Image.open(p), Image.open(aug_p)
        og, ag = gray_small(o), gray_small(g)
        fg = gray_small(o.transpose(Image.FLIP_LEFT_RIGHT))
        dd, df = float(np.abs(ag - og).mean()), float(np.abs(ag - fg).mean())
        geo = "flip" if df < dd else "none"
        n_flip += geo == "flip"
        if p.stem in pixel_set:
            pixel_diffs.append(dd)

        if p.stem in affine_set:
            ref = o.transpose(Image.FLIP_LEFT_RIGHT) if geo == "flip" else o
            s, dx, dy, ncc = best_affine(ref, ag)
            # 用恢复的仿射映射原始框（640 口径），与副本框配对算 IoU
            rows_o = load_yolo(lbl_dir / f"{p.stem}.txt")
            rows_a = load_yolo(lbl_dir / f"{p.stem}_aug0.txt")
            k = 640 / SMALL
            mapped = []
            for r in rows_o:
                cx, cy = (1 - r[1]) if geo == "flip" else r[1], r[2]
                mx = 320 + s * (cx * 640 - 320) + dx * k
                my = 320 + s * (cy * 640 - 320) + dy * k
                mapped.append((mx / 640, my / 640, r[3] * s, r[4] * s))
            used = [False] * len(rows_a)
            pic = []
            for m in mapped:
                best_d, bi = 0.15, -1
                for j, r2 in enumerate(rows_a):
                    if used[j]:
                        continue
                    d = max(abs(m[0] - r2[1]), abs(m[1] - r2[2]))
                    if d < best_d:
                        best_d, bi = d, j
                if bi >= 0:
                    used[bi] = True
                    pic.append(iou((m[0] - m[2] / 2, m[1] - m[3] / 2, m[0] + m[2] / 2, m[1] + m[3] / 2),
                                   to_xyxy(rows_a[bi])))
            aligned_ious += pic
            if pic:
                worst.append((statistics.median(pic), p.stem, geo, s, round(ncc, 3)))
            else:
                worst.append((0.0, p.stem, geo, s, round(ncc, 3)))

    min_dd = min(pixel_diffs) if pixel_diffs else 0.0
    med_iou = statistics.median(aligned_ious) if aligned_ious else 0.0
    frac07 = sum(i >= 0.7 for i in aligned_ious) / len(aligned_ious) if aligned_ious else 0.0

    if a.render_out:
        out_dir = Path(a.render_out)
        out_dir.mkdir(parents=True, exist_ok=True)
        cand = [x for x in worst if x[2] == "flip"], [x for x in worst if x[2] == "none"], sorted(worst)
        for tag, lst in [("flip", cand[0]), ("none", cand[1]), ("worst", cand[2])]:
            if not lst:
                continue
            stem = lst[0][1]
            o = Image.open(img_dir / f"{stem}.jpg").resize((640, 640))
            g = Image.open(img_dir / f"{stem}_aug0.jpg").resize((640, 640))
            draw_boxes(o, load_yolo(lbl_dir / f"{stem}.txt"), (0, 220, 0), 3)
            draw_boxes(g, load_yolo(lbl_dir / f"{stem}_aug0.txt"), (255, 40, 40), 3)
            canvas = Image.new("RGB", (o.width + g.width + 8, o.height), (255, 255, 255))
            canvas.paste(o, (0, 0))
            canvas.paste(g, (o.width + 8, 0))
            canvas.save(out_dir / f"check_{tag}_{stem[:40]}.jpg", quality=90)

    passed = (min_dd > 0.5 and med_iou >= 0.85 and frac07 >= 0.90)
    summary = {
        "pairs_total": len(origs),
        "flip_count": n_flip,
        "check1_pixel": {"n": len(pixel_diffs), "min_diff_direct": round(min_dd, 3),
                         "bug_signature_diff_zero": min_dd <= 0.5},
        "check2_affine_aligned": {"n_images": len(worst), "n_boxes": len(aligned_ious),
                                  "median_iou": round(med_iou, 4),
                                  "frac_iou_ge_0.7": round(frac07, 4)},
        "worst5_images_by_median_iou": sorted(worst)[:5],
        "PASS": passed,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if a.report:
        Path(a.report).write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    print(("[PASS] 增强产出验收通过，可入库" if passed else "[FAIL] 未达通过线，禁止入库"))


if __name__ == "__main__":
    main()
