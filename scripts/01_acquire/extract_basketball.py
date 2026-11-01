# -*- coding: utf-8 -*-
"""从下载好的 SportsMOT tar 包中提取篮球子集到 data/raw/sportsmot/。

HF 官方镜像（MCG-NJU/SportsMOT）的 tar 内是 MOT17 目录结构：
    <序列名>/img1/000001.jpg ...  <序列名>/gt/gt.txt  <序列名>/seqinfo.ini
其中 img1/（而非 OpenDataLab 版的 img/）——mot_to_yolo.py 已兼容两者。

test.tar 无 gt 标注，默认不下载、也不需要本脚本处理。

用法：
    python extract_basketball.py --hf-dir data/raw/sportsmot_hf --out-dir data/raw/sportsmot
"""
import argparse
import tarfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="SportsMOT tar -> 篮球子集目录")
    parser.add_argument("--hf-dir", default="data/raw/sportsmot_hf", help="download_sportsmot_hf.py 的输出目录")
    parser.add_argument("--out-dir", default="data/raw/sportsmot", help="提取输出目录")
    parser.add_argument("--tars", default="train.tar,val.tar", help="要处理的 tar")
    args = parser.parse_args()

    hf_dir, out_dir = Path(args.hf_dir), Path(args.out_dir)
    split_file = hf_dir / "splits_txt" / "basketball.txt"
    if not split_file.exists():
        raise SystemExit(f"[!] 缺少 {split_file}，先运行 download_sportsmot_hf.py")
    wanted = {line.strip() for line in split_file.read_text().splitlines() if line.strip()}
    print(f"目标篮球序列: {len(wanted)} 个（来自 {split_file}）")

    # 序列放在 basketball/ 子目录下，mot_to_yolo.py --sport basketball 按路径过滤才能命中
    seq_root = out_dir / "basketball"
    seq_root.mkdir(parents=True, exist_ok=True)
    extracted = set()
    for tar_name in [t.strip() for t in args.tars.split(",") if t.strip()]:
        tar_path = hf_dir / tar_name
        if not tar_path.exists():
            print(f"[SKIP] 不存在: {tar_path}")
            continue
        n = 0
        with tarfile.open(tar_path) as tf:
            for member in tf:
                name = member.name.rsplit("/", 1)[-1]
                if name.startswith("._"):  # macOS AppleDouble 元数据垃圾，不解出
                    continue
                parts = Path(member.name).parts
                # 序列名出现在路径任意层（tar 根前缀可能是 train/ 或 dataset/train/ 等）
                if not any(p in wanted for p in parts):
                    continue
                tf.extract(member, seq_root, filter="data")
                n += 1
                if member.isdir() and len(parts) >= 2 and parts[-1] in wanted:
                    extracted.add(parts[-1])
        print(f"[OK] {tar_name}: 提取 {n} 个成员")

    # 目录树降一层（若 tar 根前缀导致输出成 basketball/train/<seq>/，挪到 basketball/<seq>/）
    for prefix in ("train", "val", "dataset"):
        nested = seq_root / prefix
        if not nested.is_dir():
            continue
        for seq_dir in nested.iterdir():
            if seq_dir.is_dir() and seq_dir.name in wanted:
                target = seq_root / seq_dir.name
                if not target.exists():
                    seq_dir.rename(target)
        try:
            nested.rmdir()
        except OSError:
            pass

    ok = [d.name for d in sorted(seq_root.iterdir())
          if d.is_dir() and (d / "gt" / "gt.txt").exists()]
    missing = wanted - set(ok)
    print(f"\n完成: {len(ok)} 个含 gt 的篮球序列 -> {seq_root}")
    if missing:
        print(f"[!] 缺少 gt 的序列 {len(missing)} 个: {sorted(missing)[:5]} ...")
    print("下一步: python scripts/01_acquire/mot_to_yolo.py --sportsmot-dir data/raw/sportsmot "
          "--out-dir data/processed/vision --sport basketball --every-n 5 --min-area 400")


if __name__ == "__main__":
    main()
