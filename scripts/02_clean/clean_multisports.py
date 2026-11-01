# -*- coding: utf-8 -*-
"""MultiSports 视频清洗校验（实验 1 阶段 2：任务书点名的"视频等非结构化数据清洗"）。

校验项（每段 mp4）：
  1. cv2 可打开、首/中/尾三帧可解码（损坏检测）
  2. 实际帧数 vs GT 的 nframes（容差 ±2，容器元数据常见 ±1）
  3. 分辨率/fps 与 GT 的 resolution 一致（720p/25fps 预期）

输出（清洗前后指标，报告第 3 条素材）：
  data/processed/multisports/clean_metrics.json  —— before/after 统计 + 丢弃原因
  valid_videos.txt / bad_videos.txt             —— 保留与剔除清单

用法：
    python scripts/02_clean/clean_multisports.py \
        --video-dir data/raw/multisports/extract/basketball \
        --gt data/raw/multisports/multisports_GT.pkl
"""
import argparse
import json
import pickle
from collections import Counter
from pathlib import Path

import cv2

FPS_EXPECTED = 25
FRAME_TOL = 2


def probe(path: Path) -> tuple[bool, str, dict]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return False, "open_failed", {}
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    w, h = int(cap.get(3)), int(cap.get(4))
    # 首/中/尾三帧实解（帧数元数据可能有偏差，尾部用 grab 快进）
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ok_first, _ = cap.read()
    mid = max(0, n // 2 - 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
    ok_mid, _ = cap.read()
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, n - 3))
    ok_tail, _ = cap.read()
    cap.release()
    if not (ok_first and ok_mid and ok_tail):
        return False, "decode_failed", {"n": n, "fps": fps, "w": w, "h": h}
    return True, "", {"n": n, "fps": fps, "w": w, "h": h}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-dir", default="data/raw/multisports/extract/basketball")
    ap.add_argument("--gt", default="data/raw/multisports/multisports_GT.pkl")
    ap.add_argument("--out-dir", default="data/processed/multisports")
    args = ap.parse_args()

    with open(args.gt, "rb") as f:
        gt = pickle.load(f)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    videos = sorted(Path(args.video_dir).glob("*.mp4"))
    valid, bad, mismatch = [], [], Counter()
    for p in videos:
        vid = f"basketball/{p.stem}"
        ok, reason, info = probe(p)
        if not ok:
            bad.append((p.name, reason))
            mismatch[reason] += 1
            continue
        if vid in gt["nframes"]:
            gt_n = gt["nframes"][vid]
            gh, gw = gt["resolution"][vid]
            if abs(info["n"] - gt_n) > FRAME_TOL:
                bad.append((p.name, f"frame_count_mismatch(actual={info['n']},gt={gt_n})"))
                mismatch["frame_count_mismatch"] += 1
                continue
            if (info["w"], info["h"]) != (gw, gh):
                bad.append((p.name, f"resolution_mismatch(actual={info['w']}x{info['h']},gt={gw}x{gh})"))
                mismatch["resolution_mismatch"] += 1
                continue
        if abs(info["fps"] - FPS_EXPECTED) > 1:
            bad.append((p.name, f"fps_mismatch({info['fps']:.1f})"))
            mismatch["fps_mismatch"] += 1
            continue
        valid.append(p.name)

    metrics = {
        "videos_before": len(videos),
        "videos_after": len(valid),
        "videos_dropped": len(bad),
        "drop_reasons": dict(mismatch),
        "checks": ["open+decode(首/中/尾帧)", "帧数±2 对齐 GT", "分辨率对齐 GT", "fps≈25"],
    }
    (out_dir / "clean_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "valid_videos.txt").write_text("\n".join(valid), encoding="utf-8")
    (out_dir / "bad_videos.txt").write_text(
        "\n".join(f"{n}\t{r}" for n, r in bad), encoding="utf-8")

    print(f"视频清洗: {len(videos)} 段 -> 保留 {len(valid)}，剔除 {len(bad)}")
    if mismatch:
        print(f"  剔除原因: {dict(mismatch)}")
        for n, r in bad[:5]:
            print(f"    {n}: {r}")


if __name__ == "__main__":
    main()
