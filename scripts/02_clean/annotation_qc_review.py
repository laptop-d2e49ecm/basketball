# -*- coding: utf-8 -*-
"""标注质量审计第四关（抽样目检集构建）：自动判据三关均无法裁定"只标场上球员"这一
项目专属语义（记忆化/纹理/通用person 各有原理性死穴，见 label_qc_final.md），
改为分层抽样 + 定向复查，渲染目检拼图交人工/视觉模型裁决。

集合构成：
- 定向：A1 裁判 train 排名前 24 + 时序框数跳变帧 + GT 重复对帧 + 已知锚定帧；
- 随机：按视频分层抽 48 帧（30 个视频轮转）。
渲染：2×2 拼图（640/格），仅画 GT 绿框 + 帧名/框数，避免任何自动叠框误导裁决。

用法：python scripts/02_clean/annotation_qc_review.py [--random-n 48]
输出：data/quality/review/review_set.json + sheet_*.jpg
"""
import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
VIDEO_RE = re.compile(r"^(v_.+?_c\d+)")


def load_yolo(p: Path):
    return [[float(x) for x in l.split()] for l in p.read_text(encoding="utf-8").splitlines()
            if len(l.split()) == 5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/quality/review"))
    ap.add_argument("--random-n", type=int, default=48)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    random.seed(a.seed)

    def split_frames(split, list_file):
        return [(split, Path(l.strip()))
                for l in (ROOT / "data/splits/yolo" / list_file).read_text(encoding="utf-8").splitlines()
                if l.strip()]

    train = split_frames("train", "original_train.txt")

    # 定向集合
    audit = json.load(open(ROOT / "data/quality/annotation_audit.json", encoding="utf-8"))
    tex = json.load(open(ROOT / "data/quality/texture_audit.json", encoding="utf-8"))
    targeted = {}
    for f in audit["top100"]:
        if f["split"] == "train":
            targeted[f["stem"]] = "pass1_top"
        if len([s for s in targeted.values() if s == "pass1_top"]) >= 24:
            break
    for f in tex["top150"]:
        if "count_jump" in f and f["split"] == "train" and f["stem"] not in targeted:
            targeted[f["stem"]] = "temporal_jump"
    for f in audit["top100"]:
        if "dup_pair" in f["flags"] and f["split"] == "train" and f["stem"] not in targeted:
            targeted[f["stem"]] = "dup_pair"
    targeted["v_2j7kLB-vEEk_c001__f000450"] = "anchor_known_bad"

    path_by_stem = {p.stem: (s, p) for s, p in train}

    # 随机分层：30 视频 × 轮转
    by_video = defaultdict(list)
    for s, p in train:
        m = VIDEO_RE.match(p.stem)
        by_video[m.group(1) if m else "?"].append(p.stem)
    vids = sorted(by_video)
    random_n = []
    i = 0
    while len(random_n) < min(a.random_n, len(train)):
        v = vids[i % len(vids)]
        pool = [s for s in by_video[v] if s not in targeted and s not in random_n]
        if pool:
            random_n.append(random.choice(pool))
        i += 1
        if i > len(train):
            break

    def render_sheet(items, tag, start_idx):
        sheets = []
        for g in range(0, len(items), 4):
            batch = items[g:g + 4]
            tiles = []
            for stem in batch:
                split, p = path_by_stem[stem]
                img = Image.open(p).convert("RGB").resize((640, 640))
                d = ImageDraw.Draw(img)
                rows = load_yolo(ROOT / "data/splits/yolo/labels" / split / (stem + ".txt"))
                for r in rows:
                    cx, cy, w, h = r[1], r[2], r[3], r[4]
                    d.rectangle([(cx - w / 2) * 640, (cy - h / 2) * 640,
                                 (cx + w / 2) * 640, (cy + h / 2) * 640],
                                outline=(40, 220, 40), width=2)
                d.text((8, 6), f"{stem[:40]}  n={len(rows)}", fill=(255, 255, 0))
                tiles.append(img)
            while len(tiles) < 4:
                tiles.append(Image.new("RGB", (640, 640), (30, 30, 30)))
            sheet = Image.new("RGB", (1288, 1288), (255, 255, 255))
            for k, t in enumerate(tiles):
                sheet.paste(t, ((k % 2) * 644 + 2, (k // 2) * 644 + 2))
            fn = f"{tag}_{start_idx + g//4:02d}.jpg"
            sheet.save(out / fn, quality=88)
            sheets.append({"sheet": fn, "frames": batch})
        return sheets

    all_sheets = render_sheet(list(targeted), "targeted", 0) \
        + render_sheet(random_n, "random", 0)
    meta = {"targeted": {k: v for k, v in targeted.items()},
            "random": random_n,
            "sheets": all_sheets,
            "random_note": f"分层随机 {len(random_n)} 帧 / {len(train)} train 帧"}
    (out / "review_set.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({"targeted": len(targeted), "random": len(random_n),
                      "sheets": len(all_sheets)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
