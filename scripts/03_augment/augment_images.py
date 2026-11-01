# -*- coding: utf-8 -*-
"""任务 1.2.2：图像数据增强（检测框同步变换，防止"图像变了框没变"）。

增强策略：
- 随机水平翻转（概率 0.5）——框 cx 同步翻转：cx' = 1 - cx；
- 色彩抖动（亮度/对比度/饱和度）——不改变几何，框不动；
- 随机平移缩放（小幅仿射）——框坐标按同一几何变换重算。

优先使用 torchvision.transforms.v2（原生支持 bounding boxes）；
未安装 torchvision 时自动降级为 PIL 手工实现（翻转 + 亮度），保证可运行。

输出：images/ labels/ 原地新增 <stem>_augK.jpg/.txt，并更新 augment_log.json。
"""
import argparse
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

VISION_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "vision"

try:
    import torch  # noqa: F401
    from torchvision import tv_tensors
    from torchvision.transforms import v2
    HAS_TV_V2 = True
except Exception:  # ImportError / OSError(损坏的torch DLL) 等情况一律降级为 PIL 手工增强
    HAS_TV_V2 = False


def load_yolo(label_path: Path):
    rows = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 5:
            rows.append([float(p) for p in parts])
    return rows  # [[cls, cx, cy, w, h], ...]


def save_yolo(label_path: Path, rows):
    label_path.write_text(
        "\n".join(" ".join(f"{v:.6f}" for v in r) for r in rows), encoding="utf-8"
    )


def clip01(v):
    return min(max(v, 0.0), 1.0)


def augment_v2(img: Image.Image, rows, p_flip, affine):
    """torchvision v2 路径：翻转/仿射/色彩，框随几何同步变换。

    注意：YOLO 标签是归一化坐标，须先乘宽高转成像素 XYXY 送入 v2，
    变换后再除回宽高，否则框会塌缩到原点附近。
    """
    W, H = img.width, img.height
    boxes = tv_tensors.BoundingBoxes(
        [[(r[1] - r[3] / 2) * W, (r[2] - r[4] / 2) * H,
          (r[1] + r[3] / 2) * W, (r[2] + r[4] / 2) * H] for r in rows],
        format="XYXY", canvas_size=(H, W),
    )
    tfs = []
    if random.random() < p_flip:
        tfs.append(v2.RandomHorizontalFlip(p=1.0))
    tx, ty, scale = affine
    tfs.append(v2.RandomAffine(degrees=0, translate=(tx, ty), scale=(1 - scale, 1 + scale)))
    tfs.append(v2.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2))
    transform = v2.Compose(tfs)
    # 必须传 PIL：torchvision 0.29 的 v2 对裸 numpy 数组不生效（框被变换、图像原样返回），
    # 2026-10 实测复现；曾因此生成 2521 张"原图+错位标注"副本，见 exp3/README_HANDOFF.md 第六节
    out_img, out_boxes = transform(img, boxes)

    new_rows = []
    for i, r in enumerate(rows):
        x1, y1, x2, y2 = out_boxes[i].tolist()
        if x2 - x1 < 0.002 * W or y2 - y1 < 0.002 * H or x1 > W or y1 > H or x2 < 0 or y2 < 0:
            continue  # 变换后过小或完全出画的框丢弃
        cx, cy = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
        new_rows.append([r[0], clip01(cx), clip01(cy), clip01((x2 - x1) / W), clip01((y2 - y1) / H)])
    if not isinstance(out_img, Image.Image):
        out_img = Image.fromarray(out_img)
    return out_img, new_rows


def augment_pil(img: Image.Image, rows, p_flip, brightness_range):
    """降级路径：水平翻转 + 亮度调整（框只需处理翻转）。"""
    if random.random() < p_flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        rows = [[r[0], 1 - r[1], r[2], r[3], r[4]] for r in rows]
    factor = random.uniform(*brightness_range)
    img = ImageEnhance.Brightness(img).enhance(factor)
    return img, rows


def main():
    parser = argparse.ArgumentParser(description="检测图像增强（框同步）")
    parser.add_argument("--vision-dir", default=str(VISION_DIR))
    parser.add_argument("--times", type=int, default=1, help="每张图生成几个增强副本")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    vdir = Path(args.vision_dir)
    img_dir, label_dir = vdir / "images", vdir / "labels"
    n_src, n_out, n_dropped_boxes = 0, 0, 0

    for img_path in sorted(img_dir.glob("*.jpg")):
        if "_aug" in img_path.stem:
            continue
        label_path = label_dir / f"{img_path.stem}.txt"
        if not label_path.exists():
            continue
        rows = load_yolo(label_path)
        if not rows:
            continue
        n_src += 1
        img = Image.open(img_path).convert("RGB")

        for k in range(args.times):
            if HAS_TV_V2:
                out_img, out_rows = augment_v2(img, rows, p_flip=0.5, affine=(0.05, 0.05, 0.1))
            else:
                out_img, out_rows = augment_pil(img, rows, p_flip=0.5, brightness_range=(0.8, 1.2))
            if not out_rows:
                continue
            n_dropped_boxes += len(rows) - len(out_rows)
            stem = f"{img_path.stem}_aug{k}"
            out_img.save(img_dir / f"{stem}.jpg", quality=95)
            save_yolo(label_dir / f"{stem}.txt", out_rows)
            n_out += 1

    mode = "torchvision.transforms.v2" if HAS_TV_V2 else "PIL 降级模式（建议安装 torchvision 获得仿射增强）"
    log = {"source_images": n_src, "augmented_images": n_out, "dropped_boxes": n_dropped_boxes, "mode": mode}
    (vdir / "augment_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 模式: {mode}\n{json.dumps(log, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
