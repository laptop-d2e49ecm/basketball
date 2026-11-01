# -*- coding: utf-8 -*-
"""补充视频抽帧工具（SportsMOT 本身是图像序列，无需抽帧；自采视频时使用）。

用法：
    python extract_frames_from_video.py --video data/raw/videos/clip.mp4 \
        --out data/raw/videos/clip_frames --every-n 5 --max-frames 2000
"""
import argparse
from pathlib import Path

import cv2


def main():
    parser = argparse.ArgumentParser(description="按间隔抽取视频帧")
    parser.add_argument("--video", required=True, help="输入视频路径")
    parser.add_argument("--out", required=True, help="输出帧目录")
    parser.add_argument("--every-n", type=int, default=1, help="每 N 帧取 1 帧")
    parser.add_argument("--max-frames", type=int, default=0, help="最多保留帧数，0=不限制")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"[!] 无法打开视频: {args.video}")

    idx, saved = 0, 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % args.every_n == 0:
            cv2.imwrite(str(out_dir / f"frame_{idx:06d}.jpg"), frame)
            saved += 1
            if args.max_frames and saved >= args.max_frames:
                break
        idx += 1
    cap.release()
    print(f"[OK] 共读取 {idx} 帧，每 {args.every_n} 帧取 1 帧，保存 {saved} 帧到 {out_dir}")


if __name__ == "__main__":
    main()
