# -*- coding: utf-8 -*-
"""打 Kaggle 交接包：action_clips 数据集 + 训练/导出脚本 + 一键 Notebook + 说明。

产物（仓库根目录，上传 Kaggle 后可删）：
    action_clips_kaggle.zip          # 上传为 Kaggle Dataset（Private）
    action_clips_kaggle.zip.sha256.txt

zip 内布局（Kaggle 自动解压后即 /kaggle/input/<slug>/ 下结构）：
    action_clips/{clips,manifest.csv,meta.json,build_metrics.json}
    train_action.py / export_onnx.py / action_classes.py
    kaggle_action_train.ipynb / README_KAGGLE.md

jpg 用 STORED（不可压、写包快），文本用 DEFLATED。
"""
from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = Path(__file__).resolve().parent
DATA = ROOT / "data/action_clips"
OUT = ROOT / "action_clips_kaggle.zip"


def add(pack: zipfile.ZipFile, path: Path, arcname: str) -> None:
    compress = zipfile.ZIP_DEFLATED if path.suffix.lower() in {".py", ".md", ".ipynb", ".csv", ".json"} \
        else zipfile.ZIP_STORED
    pack.write(path, arcname, compress_type=compress)


def main() -> None:
    if not (DATA / "meta.json").is_file():
        raise SystemExit(f"数据集缺失：{DATA}（先跑 build_clips.py）")
    files = sorted(p for p in DATA.rglob("*") if p.is_file())
    print(f"数据集 {len(files)} 个文件，打包中……")
    with zipfile.ZipFile(OUT, "w") as pack:
        for i, p in enumerate(files, 1):
            add(pack, p, str(Path("action_clips") / p.relative_to(DATA)))
            if i % 20000 == 0:
                print(f"  {i}/{len(files)}", flush=True)
        for name in ("train_action.py", "export_onnx.py", "action_classes.py",
                     "kaggle_action_train.ipynb", "README_KAGGLE.md"):
            add(pack, SRC_DIR / name, name)

    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    (OUT.with_suffix(".zip.sha256.txt")).write_text(f"{digest}  {OUT.name}\n", encoding="utf-8")
    print(f"完成：{OUT}（{OUT.stat().st_size/1e6:.0f} MB，{len(files)} 数据文件 + 5 个脚本/文档）")
    print(f"SHA256: {digest}")


if __name__ == "__main__":
    sys.exit(main())
