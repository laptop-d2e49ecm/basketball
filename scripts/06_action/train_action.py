# -*- coding: utf-8 -*-
"""动作识别模型训练（实验5 视觉动作线；MultiSports 13 动作类 + 背景）。

torchvision 视频模型（mc3_18 部署档 / r2plus1d_18 精度档）+ Kinetics-400 预训练，
换 14 类头微调。数据来自 build_clips.py 产出的 clip 数据集（16 帧 × 112）。

划分纪律：官方 val（test_videos）只做最终测试；训练用官方 train 按【视频】
9:1 再切 train/valdev（同视频 clip 不跨集合，防泄漏）。训练采样按类倒数权重
平衡长尾，评测一律自然分布（逐类召回 + 混淆矩阵）。

本地冒烟：python scripts/06_action/train_action.py --fraction 0.05 --epochs 1 --batch-size 4
Kaggle 正式：python scripts/06_action/train_action.py --data-root /kaggle/input/<数据集名> \
    --work-dir /kaggle/working --device cuda:0 --arch both
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

KINETICS_MEAN = (0.43216, 0.394666, 0.37645)
KINETICS_STD = (0.22803, 0.22145, 0.216989)
ARCHS = ("mc3_18", "r2plus1d_18")


class ClipDataset(Dataset):
    def __init__(self, rows: list[dict], data_root: Path, num_frames: int, train: bool):
        self.rows = rows
        self.root = data_root
        self.num_frames = num_frames
        self.train = train

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int):
        row = self.rows[idx]
        frames = []
        for i in range(self.num_frames):
            img = Image.open(self.root / row["rel_dir"] / f"f{i:02d}.jpg").convert("RGB")
            if self.train and random.random() < 0.5:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            frames.append(np.asarray(img, dtype=np.float32) / 255.0)
        clip = torch.from_numpy(np.stack(frames))            # (T,H,W,3)
        clip = clip.permute(3, 0, 1, 2)                      # (3,T,H,W)
        mean = torch.tensor(KINETICS_MEAN).view(3, 1, 1, 1)
        std = torch.tensor(KINETICS_STD).view(3, 1, 1, 1)
        return (clip - mean) / std, int(row["label_idx"])


def build_model(arch: str, num_classes: int, pretrained: bool) -> nn.Module:
    from torchvision.models.video import MC3_18_Weights, R2Plus1D_18_Weights, mc3_18, r2plus1d_18

    if arch == "mc3_18":
        model = mc3_18(weights=MC3_18_Weights.KINETICS400_V1 if pretrained else None)
    elif arch == "r2plus1d_18":
        model = r2plus1d_18(weights=R2Plus1D_18_Weights.KINETICS400_V1 if pretrained else None)
    else:
        raise ValueError(f"未知架构 {arch}；可选 {ARCHS}")
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model


def load_rows(data_root: Path, fraction: float, seed: int) -> tuple[list[dict], list[dict], list[dict], dict]:
    meta = json.loads((data_root / "meta.json").read_text(encoding="utf-8"))
    classes = meta["classes"]
    class_to_idx = {c: i for i, c in enumerate(classes)}

    with (data_root / "manifest.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["label_idx"] = class_to_idx[r["label"]]

    # 训练集按视频 9:1 切 train/valdev（同视频 clip 不跨集合）
    rng = random.Random(seed)
    train_all = [r for r in rows if r["split"] == "train"]
    test_rows = [r for r in rows if r["split"] == "val"]
    videos = sorted({r["video_id"] for r in train_all})
    rng.shuffle(videos)
    cut = max(1, int(len(videos) * 0.9))
    dev_videos = set(videos[cut:])
    train_rows = [r for r in train_all if r["video_id"] not in dev_videos]
    dev_rows = [r for r in train_all if r["video_id"] in dev_videos]

    if fraction < 1.0:
        train_rows = rng.sample(train_rows, max(8, int(len(train_rows) * fraction)))
        dev_rows = rng.sample(dev_rows, max(4, int(len(dev_rows) * fraction)))
        test_rows = rng.sample(test_rows, max(4, int(len(test_rows) * fraction)))
    return train_rows, dev_rows, test_rows, meta


def make_loader(rows, data_root, num_frames, train, batch_size, num_workers):
    ds = ClipDataset(rows, data_root, num_frames, train=train)
    if train:
        count = Counter(r["label_idx"] for r in rows)
        weights = [1.0 / count[r["label_idx"]] for r in rows]
        sampler = WeightedRandomSampler(weights, num_samples=len(rows), replacement=True)
        return DataLoader(ds, batch_size=batch_size, sampler=sampler,
                          num_workers=num_workers, pin_memory=False, persistent_workers=num_workers > 0)
    return DataLoader(ds, batch_size=batch_size, shuffle=False,
                      num_workers=num_workers, pin_memory=False, persistent_workers=num_workers > 0)


@torch.no_grad()
def evaluate(model, loader, device, classes) -> dict:
    model.eval()
    confusion = np.zeros((len(classes), len(classes)), dtype=int)
    for clips, labels in loader:
        logits = model(clips.to(device))
        pred = logits.argmax(dim=1).cpu().numpy()
        for p, y in zip(pred, labels.numpy()):
            confusion[y, p] += 1
    total = confusion.sum()
    correct = int(np.trace(confusion))
    per_class = {}
    recalls = []
    for i, name in enumerate(classes):
        support = int(confusion[i].sum())
        recall = confusion[i, i] / support if support else float("nan")
        per_class[name] = {"recall": round(float(recall), 4) if support else None, "support": support}
        if support:
            recalls.append(recall)
    return {
        "accuracy": round(correct / total, 4) if total else None,
        "macro_recall": round(float(np.mean(recalls)), 4) if recalls else None,
        "per_class": per_class,
        "confusion_matrix": confusion.tolist(),
        "n": int(total),
    }


def train_one(arch: str, args, data_root: Path, out_root: Path, train_rows, dev_rows, test_rows, meta) -> dict:
    device = torch.device(args.device)
    out_dir = out_root / arch
    out_dir.mkdir(parents=True, exist_ok=True)
    classes = meta["classes"]
    model = build_model(arch, len(classes), pretrained=not args.no_pretrain).to(device)

    train_loader = make_loader(train_rows, data_root, meta["num_frames"], True,
                               args.batch_size, args.num_workers)
    dev_loader = make_loader(dev_rows, data_root, meta["num_frames"], False,
                             max(8, args.batch_size * 2), args.num_workers)
    test_loader = make_loader(test_rows, data_root, meta["num_frames"], False,
                              max(8, args.batch_size * 2), args.num_workers)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    steps_per_epoch = len(train_loader)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=max(1, args.epochs * steps_per_epoch))
    criterion = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler(enabled=(device.type == "cuda"))

    best = {"macro_recall": -1.0, "epoch": -1}
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        t0 = time.perf_counter()
        losses = []
        for clips, labels in train_loader:
            clips, labels = clips.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=(device.type == "cuda")):
                loss = criterion(model(clips), labels)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            losses.append(loss.item())
        dev = evaluate(model, dev_loader, device, classes)
        history.append({"epoch": epoch, "train_loss": round(float(np.mean(losses)), 4),
                        "lr": round(scheduler.get_last_lr()[0], 6),
                        "sec": round(time.perf_counter() - t0, 1), **{
                            "dev_accuracy": dev["accuracy"], "dev_macro_recall": dev["macro_recall"]}})
        print(f"[{arch}] epoch {epoch}/{args.epochs} loss {history[-1]['train_loss']:.4f} "
              f"dev acc {dev['accuracy']:.4f} macro {dev['macro_recall']:.4f} "
              f"({history[-1]['sec']}s)", flush=True)
        if dev["macro_recall"] >= best["macro_recall"]:
            best = {"macro_recall": dev["macro_recall"], "epoch": epoch}
            torch.save({"model_state": model.state_dict(), "arch": arch,
                        "classes": classes, "zh_names": meta.get("zh_names", {}),
                        "num_frames": meta["num_frames"],
                        "frame_size": meta["frame_size"], "epoch": epoch},
                       out_dir / "best.pt")

    # 最终测试（官方 val 视频集，只看一次）
    ckpt = torch.load(out_dir / "best.pt", map_location=device, weights_only=True)
    model.load_state_dict(ckpt["model_state"])
    test = evaluate(model, test_loader, device, classes)

    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)
    summary = {
        "arch": arch, "epochs": args.epochs, "batch_size": args.batch_size, "lr": args.lr,
        "pretrained": not args.no_pretrain, "best_epoch": best["epoch"],
        "train_clips": len(train_rows), "dev_clips": len(dev_rows), "test_clips": len(test_rows),
        "dev_final": dev, "test": test,
    }
    (out_dir / "train_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{arch}] best epoch {best['epoch']} | test acc {test['accuracy']} "
          f"macro {test['macro_recall']} → {out_dir}", flush=True)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="data/action_clips")
    ap.add_argument("--work-dir", default="models/exp5_action")
    ap.add_argument("--arch", default="mc3_18", choices=(*ARCHS, "both"))
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--num-workers", type=int, default=2)
    ap.add_argument("--fraction", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-pretrain", action="store_true")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)

    data_root = Path(args.data_root)
    train_rows, dev_rows, test_rows, meta = load_rows(data_root, args.fraction, args.seed)
    print(f"clips: train {len(train_rows)} / valdev {len(dev_rows)} / test {len(test_rows)}，"
          f"类别 {len(meta['classes'])}：{meta['classes']}")

    archs = ARCHS if args.arch == "both" else [args.arch]
    out_root = Path(args.work_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "data_meta_used.json").write_text(
        json.dumps({k: meta[k] for k in ("classes", "zh_names", "num_frames", "frame_size")},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    summaries = {}
    for arch in archs:
        summaries[arch] = train_one(arch, args, data_root, out_root, train_rows, dev_rows, test_rows, meta)
    (out_root / "train_summary_all.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
