# -*- coding: utf-8 -*-
"""MultiSports GT tubes → 动作识别 clip 数据集（动作线数据准备，实验5 视觉动作线）。

每个动作 tube 采样 16 帧、按逐帧 GT 框裁 112×112 球员 crop，存为 jpg；
另用部署检测器（实验2 A2' best.pt）在"无任何 tube 覆盖"的帧上取球员框，
构造 `_none` 背景类——部署时滑窗推理必须有"无动作"出口，否则会硬选一个动作。

类别归并（18 → 13 动作类 + 背景）见同目录 action_classes.py。

解码策略：按 tube 时间段（起止帧）seek 后小范围顺序读，段间缓存复用——
避免整片顺序解码的内存无界与尾部空转。

产物（--out-dir，默认 data/action_clips/）：
    clips/{split}/{label}/{clip_id}/f00.jpg ... f15.jpg
    manifest.csv   # clip_id, rel_dir, split, label, action_raw, video_id, ...
    meta.json      # 类别顺序/中文标签/采样参数（训练、导出、worker 三方共用）
    build_metrics.json

用法：
    python scripts/06_action/build_clips.py                     # 全量（约 10-20 分钟）
    python scripts/06_action/build_clips.py --videos 8          # 冒烟
    python scripts/06_action/build_clips.py --jobs 4            # 多进程
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_classes import BACKGROUND_CLASS, CLASS_MAP, meta as class_meta

ROOT = Path(__file__).resolve().parents[2]
FPS = 25
NUM_FRAMES = 16
FRAME_SIZE = 112
BOX_EXPAND = 1.2
MIN_CROP_PX = 16
BG_MARGIN_FRAMES = 8   # 背景帧与任何 tube 的最小距离
BG_WINDOW_HALF = 3     # 背景窗 = anchor ± 3 帧
BG_RESIZE_W = 640
CACHE_LIMIT = 120      # 解码帧缓存上限（全分辨率帧，超出即清空）

_worker_state: dict = {}


def _load_gt(gt_path: Path) -> dict:
    import pickle

    with open(gt_path, "rb") as f:
        return pickle.load(f)


def _split_of(gt: dict) -> dict[str, str]:
    out = {}
    for key, name in (("train_videos", "train"), ("test_videos", "val")):
        for group in gt[key]:
            for vid in (group if isinstance(group, (list, tuple)) else [group]):
                out[vid] = name
    return out


def _sample_indices(f0: int, f1: int, n: int) -> list[int]:
    """在 [f0, f1] 均匀取 n 个整数帧号（含端点，重复代表慢动作）。"""
    if f1 <= f0:
        return [f0] * n
    step = (f1 - f0) / (n - 1)
    return [min(f1, max(f0, round(f0 + i * step))) for i in range(n)]


def _tube_box_at(tube: np.ndarray, frame: int) -> np.ndarray | None:
    """tube: (n,5)[frame,x1,y1,x2,y2]，返回距 frame 最近一行的框。"""
    frames = tube[:, 0]
    idx = int(np.argmin(np.abs(frames - frame)))
    return tube[idx, 1:5]


def _expand_square(box: np.ndarray, w: int, h: int) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = box
    side = max(float(x2 - x1), float(y2 - y1)) * BOX_EXPAND
    if side < MIN_CROP_PX:
        return None
    cx, cy = (float(x1) + float(x2)) / 2, (float(y1) + float(y2)) / 2
    half = side / 2
    left, top = max(0.0, cx - half), max(0.0, cy - half)
    right, bottom = min(float(w), cx + half), min(float(h), cy + half)
    if right - left < MIN_CROP_PX or bottom - top < MIN_CROP_PX:
        return None
    return int(left), int(top), int(right), int(bottom)


def _save_clip(frames: list[np.ndarray], boxes: list[tuple[int, int, int, int] | None], out_dir: Path) -> bool:
    """对（帧, 裁剪框）序列逐帧裁剪、缩放、存盘；任一帧失败则整体丢弃。"""
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, (img, rect) in enumerate(zip(frames, boxes)):
            if img is None or rect is None or img.size == 0:
                raise ValueError("bad frame or rect")
            crop = img[rect[1]:rect[3], rect[0]:rect[2]]
            if crop.size == 0:
                raise ValueError("empty crop")
            crop = cv2.resize(crop, (FRAME_SIZE, FRAME_SIZE), interpolation=cv2.INTER_LINEAR)
            ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ok:
                raise ValueError("encode failed")
            (out_dir / f"f{i:02d}.jpg").write_bytes(buf.tobytes())
        return True
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)
        return False


class RangeDecoder:
    """按帧号区间读取视频帧，带小缓存（tubes 时间上聚集，命中率较高）。"""

    def __init__(self, video_path: Path):
        self.cap = cv2.VideoCapture(str(video_path))
        self.cache: dict[int, np.ndarray] = {}
        self.nf = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    def close(self) -> None:
        self.cache.clear()
        self.cap.release()

    def read(self, f0: int, f1: int) -> dict[int, np.ndarray]:
        """返回 {帧号: BGR图}，帧号 1 起；缺失帧跳过（调用方校验）。"""
        want = {f for f in range(f0, f1 + 1)}
        if not want.issubset(self.cache):
            if len(self.cache) + len(want) > CACHE_LIMIT:
                self.cache.clear()
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, f0 - 1)
            frame_no = f0 - 1
            while want - self.cache.keys():
                ok, img = self.cap.read()
                if not ok:
                    break
                frame_no += 1
                if frame_no in want:
                    self.cache[frame_no] = img
                elif frame_no > max(want):
                    break
        return {f: self.cache[f] for f in want if f in self.cache}

    def read_resized(self, f0: int, f1: int, width: int) -> dict[int, np.ndarray]:
        raw = self.read(f0, f1)
        out = {}
        for f, img in raw.items():
            h, w = img.shape[:2]
            if w > width:
                img = cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)
            out[f] = img
        return out


def _stretch(window: list[int], n: int) -> list[int]:
    if len(window) >= n:
        step = (len(window) - 1) / (n - 1)
        return [window[min(len(window) - 1, round(i * step))] for i in range(n)]
    out: list[int] = []
    while len(out) < n:
        out.extend(window)
    return out[:n]


def _detect_players(frame_bgr: np.ndarray) -> list[list[float]]:
    """部署检测器取单帧人框，按置信度降序（worker 进程内加载一次）。"""
    model = _worker_state.get("detector")
    if model is None:
        from ultralytics import YOLO

        model = YOLO(_worker_state["detector_path"])
        _worker_state["detector"] = model
    result = model.predict(frame_bgr, imgsz=640, verbose=False, conf=0.35,
                           device=_worker_state.get("device", "cpu"))[0]
    boxes = []
    if result.boxes is not None and len(result.boxes) > 0:
        for xyxy, conf in zip(result.boxes.xyxy.cpu().tolist(), result.boxes.conf.cpu().tolist()):
            boxes.append([float(v) for v in xyxy] + [float(conf)])
    boxes.sort(key=lambda b: -b[4])
    return boxes


def _row(clip_id, split, label, action_raw, video_id, f0, f1) -> dict:
    return {
        "clip_id": clip_id,
        "rel_dir": f"clips/{split}/{label}/{clip_id}",
        "split": split,
        "label": label,
        "action_raw": action_raw,
        "video_id": video_id,
        "start_frame": f0,
        "end_frame": f1,
        "n_frames": NUM_FRAMES,
    }


def process_video(job: dict) -> dict:
    video_id = job["video_id"]
    clip_root = Path(job["out_dir"]) / "clips"
    tubes = sorted(job["tubes"], key=lambda t: t["f0"])
    drops = Counter()
    rows = []

    decoder = RangeDecoder(Path(job["video_path"]))
    if not decoder.cap.isOpened():
        return {"video_id": video_id, "rows": [], "drops": {"video_open_fail": 1}}

    for t in tubes:
        frames = decoder.read(t["f0"], t["f1"])
        if not all(f in frames for f in set(t["frames"])):
            drops["frame_out_of_range"] += 1
            continue
        sample = frames[t["frames"][0]]
        h, w = sample.shape[:2]
        boxes = []
        ok_boxes = True
        for fr in t["frames"]:
            box = _tube_box_at(t["tube"], fr)
            rect = _expand_square(box, w, h) if box is not None else None
            if rect is None:
                ok_boxes = False
                break
            boxes.append(rect)
        if not ok_boxes:
            drops["degenerate_box"] += 1
            continue
        clip_dir = clip_root / t["split"] / t["label"] / t["clip_id"]
        if _save_clip([frames[f] for f in t["frames"]], boxes, clip_dir):
            rows.append(_row(t["clip_id"], t["split"], t["label"], t["action_raw"],
                             video_id, t["f0"], t["f1"]))
        else:
            drops["clip_io_fail"] += 1

    for a in job["bg_anchors"]:
        window = [f for f in range(a - BG_WINDOW_HALF, a + BG_WINDOW_HALF + 1) if f >= 1]
        frames = decoder.read_resized(window[0], window[-1], BG_RESIZE_W) if job["bg_anchors"] else {}
        if a not in frames:
            drops["bg_window_missing"] += 1
            continue
        boxes = _detect_players(frames[a])
        if not boxes:
            drops["bg_no_player"] += 1
            continue
        anchor = frames[a]
        rect = _expand_square(np.array(boxes[0][:4]), anchor.shape[1], anchor.shape[0])
        if rect is None:
            drops["bg_degenerate_box"] += 1
            continue
        seq = _stretch([f for f in window if f in frames], NUM_FRAMES)
        clip_id = f"{Path(video_id).stem}__bg{a:05d}"
        clip_dir = clip_root / job["split"] / BACKGROUND_CLASS / clip_id
        if _save_clip([frames[f] for f in seq], [rect] * NUM_FRAMES, clip_dir):
            rows.append(_row(clip_id, job["split"], BACKGROUND_CLASS, "", video_id, window[0], window[-1]))
        else:
            drops["clip_io_fail"] += 1
    decoder.close()

    return {"video_id": video_id, "rows": rows, "drops": dict(drops)}


def _init_worker(detector_path: str, device: str) -> None:
    _worker_state["detector_path"] = detector_path
    _worker_state["device"] = device


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", default=str(ROOT / "data/raw/multisports/multisports_GT.pkl"))
    ap.add_argument("--video-dir", default=str(ROOT / "data/raw/multisports/extract/basketball"))
    ap.add_argument("--out-dir", default=str(ROOT / "data/action_clips"))
    ap.add_argument("--detector", default=str(ROOT / "exp4/complete_web_system/backend/weights/best.pt"))
    ap.add_argument("--device", default="cpu", help="背景帧检测器设备（cpu/0）")
    ap.add_argument("--bg-anchors", type=int, default=3, help="每视频背景锚点帧数（0 关闭背景类）")
    ap.add_argument("--bg-cap", type=int, default=1200, help="背景 clip 总量上限（随机下采样）")
    ap.add_argument("--videos", type=int, default=0, help="只处理前 N 个视频（冒烟）")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--force", action="store_true", help="out-dir 已存在时清空重建")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out_dir)
    if out_dir.exists():
        if not args.force:
            raise SystemExit(f"{out_dir} 已存在；确认后加 --force 重建")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    gt = _load_gt(Path(args.gt))
    split_of = _split_of(gt)
    nframes = gt.get("nframes", {})

    jobs, tube_total, dropped_raw = [], 0, Counter()
    for vid, tubes_by_cls in sorted(gt["gttubes"].items()):
        if "basketball" not in vid:
            continue
        stem = Path(vid).stem
        video_path = Path(args.video_dir) / f"{stem}.mp4"
        if not video_path.is_file():
            continue
        split = split_of.get(vid, "train")
        tubes, ordinal = [], 0
        for cls_idx in sorted(tubes_by_cls):
            action_raw = gt["labels"][int(cls_idx)]
            label = CLASS_MAP.get(action_raw)
            if label is None:
                dropped_raw[action_raw] += len(tubes_by_cls[cls_idx])
                continue
            for tube in tubes_by_cls[cls_idx]:
                f0, f1 = int(tube[0, 0]), int(tube[-1, 0])
                if f1 - f0 + 1 < 2:
                    continue
                ordinal += 1
                tubes.append({"label": label, "action_raw": action_raw, "f0": f0, "f1": f1,
                              "split": split, "tube": tube, "clip_id": f"{stem}__t{ordinal:04d}",
                              "frames": _sample_indices(f0, f1, NUM_FRAMES)})
                tube_total += 1
        if not tubes:
            continue
        anchors = []
        if args.bg_anchors > 0:
            nf = int(nframes.get(vid, 0))
            if nf > 2 * (BG_MARGIN_FRAMES + BG_WINDOW_HALF):
                covered = set()
                for t in tubes:
                    covered.update(range(t["f0"] - BG_MARGIN_FRAMES, t["f1"] + BG_MARGIN_FRAMES + 1))
                candidates = [f for f in range(BG_MARGIN_FRAMES + BG_WINDOW_HALF + 1,
                                                nf - BG_MARGIN_FRAMES - BG_WINDOW_HALF)
                              if f not in covered]
                rng.shuffle(candidates)
                anchors = sorted(candidates[: args.bg_anchors])
        jobs.append({"video_id": vid, "video_path": str(video_path), "split": split,
                     "tubes": tubes, "bg_anchors": anchors, "out_dir": str(out_dir)})
    if args.videos:
        jobs = jobs[: args.videos]

    print(f"视频 {len(jobs)} 段 / tube {tube_total} 个（原始丢弃 {sum(dropped_raw.values())}：{dict(dropped_raw)}）")

    rows: list[dict] = []
    drops: Counter = Counter()
    done = 0
    if args.jobs <= 1:
        _init_worker(args.detector, args.device)
        for job in jobs:
            r = process_video(job)
            rows.extend(r["rows"]); drops.update(r["drops"]); done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(jobs)} 视频，clip {len(rows)}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.jobs, initializer=_init_worker,
                                 initargs=(args.detector, args.device)) as ex:
            for r in ex.map(process_video, jobs):
                rows.extend(r["rows"]); drops.update(r["drops"]); done += 1
                if done % 25 == 0:
                    print(f"  {done}/{len(jobs)} 视频，clip {len(rows)}", flush=True)

    bg_rows = [r for r in rows if r["label"] == BACKGROUND_CLASS]
    if len(bg_rows) > args.bg_cap:
        keep = {r["clip_id"] for r in rng.sample(bg_rows, args.bg_cap)}
        for r in bg_rows:
            if r["clip_id"] not in keep:
                shutil.rmtree(out_dir / "clips" / r["split"] / BACKGROUND_CLASS / r["clip_id"],
                              ignore_errors=True)
        rows = [r for r in rows if r["label"] != BACKGROUND_CLASS or r["clip_id"] in keep]

    rows.sort(key=lambda r: (r["split"], r["label"], r["clip_id"]))
    with (out_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    per_split_label = Counter((r["split"], r["label"]) for r in rows)
    meta = {
        **class_meta(),
        "num_frames": NUM_FRAMES,
        "frame_size": FRAME_SIZE,
        "fps": FPS,
        "box_expand": BOX_EXPAND,
        "detector": str(args.detector),
        "seed": args.seed,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    metrics = {
        "videos": len(jobs),
        "tubes_total": tube_total,
        "clips_kept": len(rows),
        "clips_per_split_label": {f"{s}/{l}": c for (s, l), c in sorted(per_split_label.items())},
        "raw_action_dropped": dict(dropped_raw),
        "drops": dict(drops),
        "bg_cap": args.bg_cap,
    }
    (out_dir / "build_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2),
                                                encoding="utf-8")

    print(f"完成：clip {len(rows)} 个 → {out_dir}")
    for (s, l), c in sorted(per_split_label.items()):
        print(f"  {s:5s} {l:15s} {c:5d}")
    if drops:
        print(f"  丢弃: {dict(drops)}")


if __name__ == "__main__":
    main()
