# -*- coding: utf-8 -*-
"""直播吧文字直播语料清洗与划分（实验 1 阶段 2/3，解说语料线）。

输入：data/raw/texts/livetext/*.jsonl（每场一个文件，33 字段原始记录）
输出：data/processed/texts/livetext/
    commentary.jsonl      清洗后的统一格式：game_id/live_time/text/commentator/score
    clean_metrics.json    清洗前后指标（报告第 3 条素材）
    split_{train,val,test}.jsonl   按场次 8:1:1 划分（同一场不跨集合，防泄漏）

清洗规则：
    1. 去空文本/纯表情/纯符号行；
    2. 按 (game_id, live_text, live_time) 去重；
    3. 时间戳规范化为 ISO（live_time -> YYYY-MM-DD HH:MM:SS）；
    4. 丢弃 text 长度 < 4 的碎片（"好球""哈哈"之类保留，纯"！"丢弃）。

用法：
    python scripts/02_clean/clean_livetext.py
"""
import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

RAW_DIR = Path("data/raw/texts/livetext")
OUT_DIR = Path("data/processed/texts/livetext")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=str(RAW_DIR))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--min-len", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    raw_dir, out_dir = Path(args.raw_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    games: dict[str, list[dict]] = {}
    n_raw = 0
    for f in sorted(raw_dir.glob("*.jsonl")):
        rows = []
        for line in f.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            n_raw += 1
            rows.append(e)
        if rows:
            games[f.stem] = rows

    drop = Counter()
    seen = set()
    cleaned_games = {}
    for gid, rows in games.items():
        out_rows = []
        for e in rows:
            text = (e.get("live_text") or "").strip()
            t = re.sub(r"\s+", " ", text)
            if not t:
                drop["empty"] += 1
                continue
            if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", t):  # 纯表情/符号
                drop["no_word"] += 1
                continue
            if len(t) < args.min_len:
                drop["too_short"] += 1
                continue
            lt = (e.get("live_time") or "")[:19].replace("T", " ")
            key = (gid, t, lt)
            if key in seen:
                drop["duplicate"] += 1
                continue
            seen.add(key)
            out_rows.append({
                "game_id": gid,
                "live_time": lt,
                "text": t,
                "commentator": e.get("user_chn", ""),
                "score": f"{e.get('home_score', '')}-{e.get('visit_score', '')}",
            })
        if out_rows:
            cleaned_games[gid] = out_rows

    # 按场次 8:1:1（场次级划分，同场不跨集合）
    gids = sorted(cleaned_games)
    random.Random(args.seed).shuffle(gids)
    n = len(gids)
    n_test = max(1, round(n * 0.1)) if n >= 3 else 1
    n_val = max(1, round(n * 0.1)) if n >= 3 else 1
    test_ids = set(gids[:n_test])
    val_ids = set(gids[n_test:n_test + n_val])
    splits = {"train": [], "val": [], "test": []}
    all_rows = []
    for gid in gids:
        part = "test" if gid in test_ids else ("val" if gid in val_ids else "train")
        splits[part].extend(cleaned_games[gid])
        all_rows.extend(cleaned_games[gid])

    all_rows.sort(key=lambda r: (r["game_id"], r["live_time"]))
    with (out_dir / "commentary.jsonl").open("w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    split_stat = {}
    for part, rows in splits.items():
        with (out_dir / f"split_{part}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        split_stat[part] = {"games": len({r["game_id"] for r in rows}), "entries": len(rows)}

    metrics = {
        "games_with_text": len(cleaned_games),
        "entries_before": n_raw,
        "entries_after": len(all_rows),
        "entries_dropped": dict(drop),
        "split_8_1_1_by_game": split_stat,
    }
    (out_dir / "clean_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"清洗: {n_raw} -> {len(all_rows)} 条（{len(cleaned_games)} 场），丢弃 {dict(drop)}")
    print(f"划分(按场次): {split_stat}")


if __name__ == "__main__":
    main()
