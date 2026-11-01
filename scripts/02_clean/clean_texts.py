# -*- coding: utf-8 -*-
"""任务 1.2.1（第 2 条）：非结构化文本清洗与规范化。

处理：HTML 实体还原、多余空白、特殊不可见字符、全角转半角（ASCII 部分）、
URL 邮箱剔除、过长/过短文档过滤。
输入：data/raw/texts/*.txt（爬虫产出）
输出：data/processed/texts/*.txt + clean_metrics.json + cleaned.jsonl（Data-Juicer 对比用）
"""
import argparse
import html
import json
import re
import time
from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "texts"
OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "texts"

URL_RE = re.compile(r"https?://\S+")
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\ufeff]")
MULTISPACE_RE = re.compile(r"[ \t\u3000]+")


def normalize(text: str) -> str:
    text = html.unescape(text)
    text = URL_RE.sub("", text)
    text = EMAIL_RE.sub("", text)
    text = INVISIBLE_RE.sub("", text)
    # 全角 ASCII 转半角（\uFF01-\uFF5E -> 对应 ASCII）
    text = "".join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in text)
    text = MULTISPACE_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def main():
    parser = argparse.ArgumentParser(description="文本清洗与规范化")
    parser.add_argument("--raw-dir", default=str(RAW_DIR))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--min-chars", type=int, default=50, help="短于该字数的文档丢弃")
    args = parser.parse_args()

    raw_dir, out_dir = Path(args.raw_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    metrics = {"total": 0, "kept": 0, "dropped_short": 0, "chars_before": 0, "chars_after": 0}
    jsonl = out_dir / "cleaned.jsonl"
    with jsonl.open("w", encoding="utf-8") as jf:
        for txt_path in sorted(raw_dir.glob("*.txt")):
            metrics["total"] += 1
            text = txt_path.read_text(encoding="utf-8", errors="ignore")
            metrics["chars_before"] += len(text)
            cleaned = normalize(text)
            if len(cleaned) < args.min_chars:
                metrics["dropped_short"] += 1
                continue
            metrics["kept"] += 1
            metrics["chars_after"] += len(cleaned)
            (out_dir / txt_path.name).write_text(cleaned, encoding="utf-8")
            jf.write(json.dumps({"text": cleaned, "source": txt_path.stem}, ensure_ascii=False) + "\n")

    metrics["seconds"] = round(time.time() - t0, 2)  # 手工清洗耗时基准，与 Data-Juicer 对比
    (out_dir / "clean_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
