# -*- coding: utf-8 -*-
"""MultiSports GT 标注 → 解说事件表 CSV（采集线①核心转换之一）。

每个动作实例（tube）输出一行，字段按任务书 1.3.1 口径（小写下划线）：
    video_id, split, action, action_id,
    start_frame, end_frame, start_time, end_time, duration_frames,
    video_nframes, video_w, video_h,
    box_x1, box_y1, box_x2, box_y2        # 事件起始帧的球员框（像素）
    box_cx_norm, box_cy_norm               # 框中心归一化位置（场上落点粗粒度）

同时输出标注清洗指标（clean_metrics）：
    tube 总数 / 保留 / 丢弃原因分布（帧号越界、退化框、超短视频）——报告"清洗前后指标"素材。

用法：
    python scripts/01_acquire/multisports_to_events.py \
        --gt data/raw/multisports/multisports_GT.pkl \
        --out-dir data/processed/multisports
"""
import argparse
import csv
import pickle
from collections import Counter
from pathlib import Path

FPS = 25  # MultiSports 统一 25fps（同 SportsMOT）


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default="data/raw/multisports/multisports_GT.pkl")
    ap.add_argument("--out-dir", default="data/processed/multisports")
    ap.add_argument("--min-box-area", type=int, default=400,
                    help="起始帧框最小面积（像素），小于此视为退化框丢弃")
    args = ap.parse_args()

    with open(args.gt, "rb") as f:
        gt = pickle.load(f)
    labels = gt["labels"]
    split_of = {}
    for split_key, sname in (("train_videos", "train"), ("test_videos", "val")):
        for group in gt[split_key]:  # 每个划分是"按运动分组的嵌套列表"
            for v in (group if isinstance(group, (list, tuple)) else [group]):
                split_of[v] = sname

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, drop = [], Counter()
    for vid, tubes_by_cls in gt["gttubes"].items():
        if "basketball" not in vid:
            continue
        nf = gt["nframes"].get(vid, 0)
        h, w = gt["resolution"].get(vid, (0, 0))
        for cls_idx, tubes in tubes_by_cls.items():
            action = labels[int(cls_idx)]
            for tube in tubes:  # tube: (n,5) [frame,x1,y1,x2,y2] float32
                f0, f1 = int(tube[0, 0]), int(tube[-1, 0])
                x1, y1, x2, y2 = (float(v) for v in tube[0, 1:5])
                if nf and (f0 < 1 or f1 > nf):
                    drop["frame_out_of_range"] += 1
                    continue
                if x2 - x1 < 2 or y2 - y1 < 2 or (x2 - x1) * (y2 - y1) < args.min_box_area:
                    drop["degenerate_box"] += 1
                    continue
                if f1 - f0 + 1 < 2:
                    drop["too_short"] += 1
                    continue
                rows.append({
                    "video_id": vid,
                    "split": split_of.get(vid, "unknown"),
                    "action": action,
                    "action_id": int(cls_idx),
                    "start_frame": f0,
                    "end_frame": f1,
                    "start_time": round(f0 / FPS, 3),
                    "end_time": round(f1 / FPS, 3),
                    "duration_frames": f1 - f0 + 1,
                    "video_nframes": nf,
                    "video_w": w,
                    "video_h": h,
                    "box_x1": round(x1, 1),
                    "box_y1": round(y1, 1),
                    "box_x2": round(x2, 1),
                    "box_y2": round(y2, 1),
                    "box_cx_norm": round((x1 + x2) / 2 / w, 4) if w else "",
                    "box_cy_norm": round((y1 + y2) / 2 / h, 4) if h else "",
                })

    rows.sort(key=lambda r: (r["video_id"], r["start_frame"]))
    csv_path = out_dir / "events.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows) + sum(drop.values())
    per_split = Counter(r["split"] for r in rows)
    per_action = Counter(r["action"] for r in rows)
    metrics = {
        "tube_total": total,
        "events_kept": len(rows),
        "events_dropped": dict(drop),
        "per_split": dict(per_split),
        "per_action": dict(per_action.most_common()),
        "csv": str(csv_path),
    }
    import json
    (out_dir / "events_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"事件表: {csv_path}（{len(rows)} 行 / 原始 {total} 个 tube，丢弃 {sum(drop.values())}）")
    print(f"  丢弃原因: {dict(drop) if drop else '无'}")
    print(f"  split 分布: {dict(per_split)}")
    for a, c in per_action.most_common(5):
        print(f"  {c:5d}  {a}")


if __name__ == "__main__":
    main()
