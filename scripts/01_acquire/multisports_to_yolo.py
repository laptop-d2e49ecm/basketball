# -*- coding: utf-8 -*-
"""MultiSports 视频 → 抽帧图像 + tube 框 → YOLO 训练数据（"视频中截取的图像"管道）。

产出（供实验 2 检测训练的补充数据源，与 SportsMOT 的 data/splits/yolo 并存）：
    <out-dir>/images/<video>__f<帧号:06d>.jpg   抽帧图像（默认每 12 帧取 1，约 2fps）
    <out-dir>/labels/<同名>.txt                 YOLO 格式：`0 cx cy w h`（归一化）

关键口径：
  - 只保留"该帧至少被一个 tube 覆盖"的帧——tube 只标注做动作的球员，
    无标注帧里的大量球员会被当成背景（假阴性），不能进训练集；
  - 即便如此，被保留帧里仍有未标注球员，故本数据定位为 SportsMOT 完整标注的
    **补充源**（实验 2 可做 有/无 消融），不是替代；
  - 类别只有 0=player（检测任务不区分手部动作）。

用法：
    python scripts/01_acquire/multisports_to_yolo.py \
        --gt data/raw/multisports/multisports_GT.pkl \
        --video-dir data/raw/multisports/extract/basketball \
        --out-dir data/processed/vision_ms --split train --every-n 12
"""
import argparse
import json
import pickle
from collections import defaultdict
from pathlib import Path

import cv2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="data/raw/multisports/multisports_GT.pkl")
    ap.add_argument("--video-dir", default="data/raw/multisports/extract/basketball")
    ap.add_argument("--out-dir", default="data/processed/vision_ms")
    ap.add_argument("--split", default="train", choices=["train", "val", "both"])
    ap.add_argument("--every-n", type=int, default=12, help="每 N 帧采样 1 帧（默认 12 ≈ 2fps）")
    ap.add_argument("--min-area", type=int, default=400)
    ap.add_argument("--limit-videos", type=int, default=0, help=">0 时只处理前 N 段（调试用）")
    args = ap.parse_args()

    with open(args.gt, "rb") as f:
        gt = pickle.load(f)

    # split -> 视频名集合
    split_videos = set()
    for split_key, sname in (("train_videos", "train"), ("test_videos", "val")):
        if args.split in (sname, "both"):
            for group in gt[split_key]:
                for v in (group if isinstance(group, (list, tuple)) else [group]):
                    if "basketball" in v:
                        split_videos.add(v.split("/", 1)[1])

    # video -> {frame -> [(x1,y1,x2,y2), ...]}
    tube_at = defaultdict(lambda: defaultdict(list))
    for vid, by_cls in gt["gttubes"].items():
        if "basketball" not in vid:
            continue
        name = vid.split("/", 1)[1]
        for tubes in by_cls.values():
            for tube in tubes:
                for row in tube:
                    fno = int(row[0])
                    x1, y1, x2, y2 = (float(v) for v in row[1:5])
                    tube_at[name][fno].append((x1, y1, x2, y2))

    img_dir = Path(args.out_dir) / "images"
    lbl_dir = Path(args.out_dir) / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    stats = {"videos": 0, "frames_sampled": 0, "frames_kept": 0, "boxes_written": 0, "skipped_no_tube": 0}
    todo = sorted(split_videos & {p.stem for p in Path(args.video_dir).glob("*.mp4")})
    if args.limit_videos:
        todo = todo[: args.limit_videos]
    missing = len(split_videos) - len(todo)
    if missing:
        print(f"[WARN] {missing} 段视频文件缺失（test.tar 未解压时 val 段不在），仅处理现有 {len(todo)} 段")

    for name in todo:
        frames_map = tube_at.get(name)
        if not frames_map:
            stats["skipped_no_tube"] += 1
            continue
        cap = cv2.VideoCapture(str(Path(args.video_dir) / f"{name}.mp4"))
        if not cap.isOpened():
            print(f"[WARN] 打开失败: {name}")
            continue
        stats["videos"] += 1
        fno = 0
        while True:
            if fno % args.every_n == 0:
                ok, frame = cap.read()
                if not ok:
                    break
                stats["frames_sampled"] += 1
                boxes = frames_map.get(fno + 1, [])  # tube 帧号从 1 起
                h, w = frame.shape[:2]
                lines = []
                for x1, y1, x2, y2 in boxes:
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    if (x2 - x1) * (y2 - y1) < args.min_area:
                        continue
                    cx, cy = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h
                    bw, bh = (x2 - x1) / w, (y2 - y1) / h
                    lines.append(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                if lines:
                    stem = f"{name}__f{fno:06d}"
                    cv2.imwrite(str(img_dir / f"{stem}.jpg"), frame,
                                [cv2.IMWRITE_JPEG_QUALITY, 92])
                    (lbl_dir / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
                    stats["frames_kept"] += 1
                    stats["boxes_written"] += len(lines)
            else:
                if not cap.grab():  # 跳帧不解码
                    break
            fno += 1
        cap.release()
        if stats["videos"] % 50 == 0:
            print(f"  已处理 {stats['videos']} 段，保留 {stats['frames_kept']} 帧", flush=True)

    metrics_path = Path(args.out_dir) / "convert_metrics.json"
    metrics_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 处理 {stats['videos']} 段视频 -> 保留 {stats['frames_kept']} 帧 / "
          f"{stats['boxes_written']} 个框（采样 {stats['frames_sampled']} 帧，"
          f"无 tube 跳过 {stats['skipped_no_tube']} 段）")
    print(f"     指标已存 {metrics_path}")


if __name__ == "__main__":
    main()
