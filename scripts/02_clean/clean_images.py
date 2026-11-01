# -*- coding: utf-8 -*-
"""任务 1.2.1（第 3/4 条）：图像/视频帧数据清洗 + 标注校验 + 元数据隐私清理。

步骤：
1. 损坏图像检测：无法解码的移入 quarantine/；
2. 隐私保护：重写 JPEG 抹除 EXIF 等元数据（任务书"元数据清理（隐私保护）"）；
3. 近似重复帧检测：感知哈希（imagehash，缺省时降级为 dhash 自实现），
   汉明距离 <= 阈值的视为重复，保留组内第一张，其余连同标签移入 quarantine/；
4. 标注校验：YOLO 标签坐标越界 / 宽高非正的帧视为"图像-标注不一致"，移入 quarantine/。

输出：data/processed/vision/clean_metrics.json（报告第 3 条引用）。
"""
import argparse
import json
import shutil
from pathlib import Path

from PIL import Image

try:
    from imagehash import phash as perceptual_hash
    HAS_IMAGEHASH = True
except ImportError:
    HAS_IMAGEHASH = False

VISION_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "vision"


def dhash_fallback(img: Image.Image, size: int = 8) -> int:
    """imagehash 缺失时的简易 dhash（差异哈希），返回 int 便于异或求距离。"""
    g = img.convert("L").resize((size + 1, size))
    pixels = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left = pixels[row * (size + 1) + col]
            right = pixels[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def image_hash(img: Image.Image):
    return perceptual_hash(img) if HAS_IMAGEHASH else dhash_fallback(img)


def hamming(a, b) -> int:
    if HAS_IMAGEHASH:
        return a - b
    return bin(a ^ b).count("1")


def strip_exif(img_path: Path) -> bool:
    """重写图像以抹除 EXIF 元数据；返回是否发生重写。"""
    with Image.open(img_path) as im:
        if not im.getexif():
            return False
        im.save(img_path)  # PIL 默认不保留 EXIF
    return True


def label_valid(label_path: Path) -> bool:
    """校验 YOLO 标签：每行 5 列、坐标在 [0,1]、宽高为正。"""
    if not label_path.exists():
        return False
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            return False
        try:
            _cls, cx, cy, w, h = (float(p) for p in parts)
        except ValueError:
            return False
        if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="图像清洗：损坏/重复/元数据/标注校验")
    parser.add_argument("--vision-dir", default=str(VISION_DIR), help="含 images/ labels/ 的目录")
    parser.add_argument("--hash-th", type=int, default=6, help="感知哈希汉明距离阈值，<= 视为重复")
    parser.add_argument("--dry-run", action="store_true", help="只统计不移动文件")
    args = parser.parse_args()

    vdir = Path(args.vision_dir)
    img_dir, label_dir = vdir / "images", vdir / "labels"
    quarantine = vdir / "quarantine"
    if not args.dry_run:
        (quarantine / "images").mkdir(parents=True, exist_ok=True)
        (quarantine / "labels").mkdir(parents=True, exist_ok=True)

    metrics = {"total": 0, "corrupt": 0, "exif_stripped": 0, "near_duplicates": 0, "bad_labels": 0, "kept": 0}
    hashes = []  # [(hash, path)] 供近重复比较

    for img_path in sorted(img_dir.glob("*.jpg")):
        metrics["total"] += 1
        label_path = label_dir / f"{img_path.stem}.txt"

        # 1) 损坏检测
        try:
            img = Image.open(img_path)
            img.load()
        except Exception:
            metrics["corrupt"] += 1
            if not args.dry_run:
                shutil.move(str(img_path), quarantine / "images" / img_path.name)
                if label_path.exists():
                    shutil.move(str(label_path), quarantine / "labels" / label_path.name)
            continue

        # 2) 元数据清理（隐私）
        if strip_exif(img_path):
            metrics["exif_stripped"] += 1

        # 3) 近似重复帧
        with Image.open(img_path) as im:
            h = image_hash(im)
        dup = any(hamming(h, prev) <= args.hash_th for prev, _ in hashes)
        if dup:
            metrics["near_duplicates"] += 1
            if not args.dry_run:
                shutil.move(str(img_path), quarantine / "images" / img_path.name)
                if label_path.exists():
                    shutil.move(str(label_path), quarantine / "labels" / label_path.name)
            continue
        hashes.append((h, img_path))

        # 4) 标注校验
        if not label_valid(label_path):
            metrics["bad_labels"] += 1
            if not args.dry_run:
                shutil.move(str(img_path), quarantine / "images" / img_path.name)
                if label_path.exists():
                    shutil.move(str(label_path), quarantine / "labels" / label_path.name)
            continue

        metrics["kept"] += 1

    out = vdir / "clean_metrics.json"
    out.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"指标已写入 {out}" + ("（dry-run 模式，未实际移动文件）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
