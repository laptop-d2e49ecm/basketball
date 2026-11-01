# -*- coding: utf-8 -*-
"""任务 1.3：数据标准化 + 8:1:1 划分 + YOLO 目录结构生成。

三类数据统一处理：
1. 视觉数据：按【序列】为单位划分 8:1:1（同一序列相邻帧几乎相同，按帧随机切
   会造成训练/测试集泄漏——这一点写入报告是加分讨论点）；图像统一缩放到
   --imgsz（默认 640；归一化框坐标不随缩放变化）；输出标准 YOLO 目录：
       data/splits/yolo/images/{train,val,test}/
       data/splits/yolo/labels/{train,val,test}/
2. 结构化数据：字段已转小写 snake_case、数值列已在增强阶段 Min-Max 归一化，
   此处按行随机划分（固定随机种子）；
3. 文本数据：cleaned.jsonl 按 8:1:1 划分。

输出：data/splits/split_summary.json（各集合样本数统计，报告引用）。
"""
import argparse
import json
import random
import re
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
VISION_DIR = ROOT / "data" / "processed" / "vision"
STRUCT_DIR = ROOT / "data" / "processed" / "structured"
TEXT_DIR = ROOT / "data" / "processed" / "texts"
SPLIT_DIR = ROOT / "data" / "splits"


def snake_case(name: str) -> str:
    name = name.strip().replace("-", "_").replace(" ", "_")
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return re.sub(r"[^0-9a-zA-Z_\u4e00-\u9fff]+", "_", name).lower()


def split_list(items, ratio=(0.8, 0.1, 0.1)):
    items = list(items)
    random.shuffle(items)
    n = len(items)
    n_train = round(n * ratio[0])
    n_val = round(n * ratio[1])
    return items[:n_train], items[n_train:n_train + n_val], items[n_train + n_val:]


def split_vision(imgsz: int):
    img_dir, label_dir = VISION_DIR / "images", VISION_DIR / "labels"
    images = [p for p in img_dir.glob("*.jpg")]
    if not images:
        print("[!] 没有视觉数据（data/processed/vision/images 为空），跳过")
        return None

    # 文件名形如 <seq>__f000123.jpg 或 <seq>__f000123_aug0.jpg -> 序列 = "__" 前的部分
    seq_of = {p.name: p.stem.split("__")[0] for p in images}
    sequences = sorted(set(seq_of.values()))
    train_seqs, val_seqs, test_seqs = split_list(sequences)
    seq2split = {s: sp for sp, seqs in [("train", train_seqs), ("val", val_seqs), ("test", test_seqs)] for s in seqs}

    counts = {"train": 0, "val": 0, "test": 0}
    for split in counts:
        (SPLIT_DIR / "yolo" / "images" / split).mkdir(parents=True, exist_ok=True)
        (SPLIT_DIR / "yolo" / "labels" / split).mkdir(parents=True, exist_ok=True)

    for img_path in images:
        split = seq2split[seq_of[img_path.name]]
        # 标准化：统一尺寸（YOLO 常用 640，归一化坐标不变；如需保持宽高比可改 letterbox）
        with Image.open(img_path) as im:
            im.convert("RGB").resize((imgsz, imgsz), Image.LANCZOS).save(
                SPLIT_DIR / "yolo" / "images" / split / img_path.name, quality=95
            )
        label_path = label_dir / f"{img_path.stem}.txt"
        if label_path.exists():
            shutil.copy2(label_path, SPLIT_DIR / "yolo" / "labels" / split / label_path.name)
        counts[split] += 1

    return {
        "n_sequences": len(sequences),
        "sequences_train": len(train_seqs),
        "sequences_val": len(val_seqs),
        "sequences_test": len(test_seqs),
        "images": counts,
        "imgsz": imgsz,
        "split_unit": "sequence",
    }


def split_structured():
    files = sorted(STRUCT_DIR.glob("*_augmented.csv")) or sorted(STRUCT_DIR.glob("*_clean.csv"))
    if not files:
        print("[!] 没有结构化数据，跳过")
        return None
    result = {}
    out_dir = SPLIT_DIR / "structured"
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        import pandas as pd

        df = pd.read_csv(f)
        df.columns = [snake_case(c) for c in df.columns]  # 字段小写 snake_case
        rows = df.index.tolist()
        tr, va, te = split_list(rows)
        stem = f.stem.replace("_augmented", "").replace("_clean", "")
        df.iloc[tr].to_csv(out_dir / f"{stem}_train.csv", index=False, encoding="utf-8-sig")
        df.iloc[va].to_csv(out_dir / f"{stem}_val.csv", index=False, encoding="utf-8-sig")
        df.iloc[te].to_csv(out_dir / f"{stem}_test.csv", index=False, encoding="utf-8-sig")
        result[f.name] = {"train": len(tr), "val": len(va), "test": len(te), "columns": list(df.columns)}
    return result


def split_texts():
    src = TEXT_DIR / "cleaned.jsonl"
    if not src.exists():
        print("[!] 没有清洗后的文本（cleaned.jsonl），跳过")
        return None
    docs = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    tr, va, te = split_list(docs)
    out_dir = SPLIT_DIR / "texts"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, part in [("train", tr), ("val", va), ("test", te)]:
        # 标准化格式：{"text": ..., "label": ...}（任务 1.3.1 文本 JSON 要求）
        with (out_dir / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for d in part:
                f.write(json.dumps({"text": d["text"], "label": d.get("label", "basketball_news")}, ensure_ascii=False) + "\n")
    return {"train": len(tr), "val": len(va), "test": len(te)}


def main():
    parser = argparse.ArgumentParser(description="标准化与 8:1:1 划分")
    parser.add_argument("--imgsz", type=int, default=640, help="视觉数据统一边长")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)

    summary = {
        "vision": split_vision(args.imgsz),
        "structured": split_structured(),
        "texts": split_texts(),
        "seed": args.seed,
        "ratio": "8:1:1",
    }
    out = SPLIT_DIR / "split_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n划分汇总 -> {out}")
    print("YOLO 目录结构（实验 2 直接指向 data/splits/yolo 训练）已生成。")


if __name__ == "__main__":
    main()
