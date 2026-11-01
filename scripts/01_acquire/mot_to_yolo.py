# -*- coding: utf-8 -*-
"""任务 1.1.2 + 衔接实验 2：SportsMOT（MOT 格式）转 YOLO 检测格式。

SportsMOT 每个序列目录结构：
    <序列>/img/000001.jpg ...   （已按帧编号的图像序列）
    <序列>/gt/gt.txt            （MOT 格式：frame,id,x,y,w,h,conf,x,y,z[,vis]）

本脚本：
1. 递归查找含 img/ 的序列目录（--sport basketball 可按路径关键字过滤）；
2. 每 N 帧抽样，过滤面积过小的框；
3. 框坐标从 (x,y,w,h) 像素转 YOLO 归一化 (cx,cy,w,h)，类别固定为 player=0；
4. 输出到 data/processed/vision/{images,labels}/，文件名带序列前缀防冲突；
5. 生成 manifest.json（序列→帧数/框数），供阶段 3"按序列划分 8:1:1"使用。

用法：
    python mot_to_yolo.py --sportsmot-dir data/raw/sportsmot \
        --out-dir data/processed/vision --sport basketball --every-n 5 --min-area 400
"""
import argparse
import json
import shutil
from pathlib import Path

import cv2

CLASS_ID = 0  # 0=player（如后续细分 referee/ball，在此扩展类别表）


def find_sequence_dirs(root: Path, sport: str):
    """递归查找所有含 img/ 或 img1/ 子目录的序列目录，可按路径中的运动关键字过滤。"""
    seq_dirs = {p.parent for name in ("img", "img1") for p in root.rglob(name) if p.is_dir()}
    if sport:
        seq_dirs = {d for d in seq_dirs if sport.lower() in str(d).lower()}
    return sorted(seq_dirs)


def load_gt(gt_path: Path, min_area: float, vis_th: float):
    """读 MOT gt.txt，返回 {frame_idx: [(x,y,w,h), ...]}（已按面积/可见度过滤）。"""
    boxes_by_frame = {}
    for line in gt_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().split(",")
        if len(parts) < 6:
            continue
        try:
            frame, _tid = int(float(parts[0])), int(float(parts[1]))
            x, y, w, h = (float(parts[i]) for i in range(2, 6))
        except ValueError:
            continue
        if vis_th >= 0 and len(parts) >= 10:
            try:
                if float(parts[9]) < vis_th:
                    continue
            except ValueError:
                pass
        if w * h < min_area:
            continue
        boxes_by_frame.setdefault(frame, []).append((x, y, w, h))
    return boxes_by_frame


def frame_images(img_dir: Path):
    """排序后的帧图像列表（过滤 macOS 打包产生的 ._ AppleDouble 垃圾文件）。"""
    return sorted(p for p in img_dir.glob("*.jpg") if not p.name.startswith("._"))


def convert_sequence(seq_dir: Path, out_dir: Path, every_n: int, min_area: float, vis_th: float):
    img_dir = seq_dir / "img" if (seq_dir / "img").is_dir() else seq_dir / "img1"
    gt_path = seq_dir / "gt" / "gt.txt"
    if not gt_path.exists():
        print(f"[SKIP] 缺少 gt/gt.txt: {seq_dir}")
        return None

    boxes_by_frame = load_gt(gt_path, min_area, vis_th)

    # 用第一张图确定该序列图像尺寸（MOT 框为像素坐标，需按尺寸归一化）
    frames = frame_images(img_dir)
    first_img = frames[0] if frames else None
    if first_img is None:
        print(f"[SKIP] 无图像帧: {seq_dir}")
        return None
    img0 = cv2.imread(str(first_img))
    if img0 is None:
        print(f"[SKIP] 图像损坏: {first_img}")
        return None
    H, W = img0.shape[:2]

    seq_name = seq_dir.name
    n_frames, n_boxes = 0, 0
    for img_path in frames:
        frame_idx = int(img_path.stem)
        if frame_idx % every_n != 0:
            continue
        boxes = boxes_by_frame.get(frame_idx, [])
        if not boxes:  # 没有标注的帧不进训练集
            continue

        out_stem = f"{seq_name}__f{frame_idx:06d}"
        shutil.copy2(img_path, out_dir / "images" / f"{out_stem}.jpg")
        lines = []
        for x, y, w, h in boxes:
            cx, cy = (x + w / 2) / W, (y + h / 2) / H
            lines.append(f"{CLASS_ID} {cx:.6f} {cy:.6f} {w / W:.6f} {h / H:.6f}")
        (out_dir / "labels" / f"{out_stem}.txt").write_text("\n".join(lines), encoding="utf-8")
        n_frames += 1
        n_boxes += len(boxes)

    return {"sequence": seq_name, "frames_sampled": n_frames, "boxes": n_boxes, "img_w": W, "img_h": H}


def main():
    parser = argparse.ArgumentParser(description="SportsMOT -> YOLO 转换与帧抽样")
    parser.add_argument("--sportsmot-dir", required=True, help="SportsMOT 解压根目录")
    parser.add_argument("--out-dir", required=True, help="输出目录（含 images/ labels/）")
    parser.add_argument("--sport", default="", help="按路径关键字过滤运动类别，如 basketball")
    parser.add_argument("--every-n", type=int, default=5, help="每 N 帧取 1 帧")
    parser.add_argument("--min-area", type=float, default=400.0, help="框最小像素面积，过滤过小目标")
    parser.add_argument("--vis-th", type=float, default=-1, help="可见度阈值（gt 第10列），-1=不过滤")
    parser.add_argument("--limit-seqs", type=int, default=0, help="最多处理多少个序列，0=全部")
    args = parser.parse_args()

    root = Path(args.sportsmot_dir)
    out_dir = Path(args.out_dir)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "labels").mkdir(parents=True, exist_ok=True)

    seq_dirs = find_sequence_dirs(root, args.sport)
    if args.limit_seqs:
        seq_dirs = seq_dirs[: args.limit_seqs]
    if not seq_dirs:
        raise SystemExit(f"[!] 在 {root} 下没找到含 img/ 的序列目录（sport 过滤: {args.sport}）")

    manifest = []
    for seq_dir in seq_dirs:
        rec = convert_sequence(seq_dir, out_dir, args.every_n, args.min_area, args.vis_th)
        if rec:
            manifest.append(rec)
            print(f"[OK] {rec['sequence']}: 抽样 {rec['frames_sampled']} 帧 / {rec['boxes']} 框")

    total_frames = sum(r["frames_sampled"] for r in manifest)
    total_boxes = sum(r["boxes"] for r in manifest)
    result = {
        "source": "SportsMOT",
        "sport_filter": args.sport,
        "every_n": args.every_n,
        "min_area": args.min_area,
        "sequences": len(manifest),
        "total_frames": total_frames,
        "total_boxes": total_boxes,
        "detail": manifest,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成：{len(manifest)} 个序列，{total_frames} 帧，{total_boxes} 框 -> {manifest_path}")


if __name__ == "__main__":
    main()
