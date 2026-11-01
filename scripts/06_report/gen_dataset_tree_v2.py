# -*- coding: utf-8 -*-
"""生成实验1报告 图1：最终数据集目录结构（三条数据线 v2，2026-10-18 现行布局）。

旧版 fig4_dataset_tree.png 画的是已废弃方案（结构化 CSV 已删、无 MultiSports/
解说语料线），本脚本按当前 data/ 真实落盘结构重绘。输出覆盖同名文件。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "report/figures/fig4_dataset_tree.png"

F_TITLE = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 30)
F_BOLD = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 22)
F_TEXT = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
F_SMALL = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)

# (路径树文本, 右侧注释, 是否加粗分层标题)
LINES = [
    ("data/", "数据根目录（处理链路与版本见 docs/PROVENANCE.md）", False),
    ("├─ raw/", "① 原始层：只读留存，任意一步可复现", True),
    ("│  ├─ multisports/extract/basketball/", "526 段比赛视频 mp4（官方 train 379 / val 147）", False),
    ("│  ├─ multisports/multisports_GT.pkl", "官方标注：逐帧球员框 + 18 类动作实例", False),
    ("│  └─ texts/livetext/*.jsonl", "41 场文字直播原始 JSONL（33 字段/条）", False),
    ("├─ processed/", "② 清洗层：每条数据线 clean_metrics.json 落盘", True),
    ("│  ├─ multisports/events.csv", "事件表：6247 行动作实例（动作/起止时间/位置）", False),
    ("│  ├─ vision_ms/{images,labels}/", "视频截帧补充检测集：7746 帧 / 9094 框", False),
    ("│  └─ texts/livetext/", "解说清洗与三分卷", False),
    ("│     ├─ commentary.jsonl", "40376 条清洗后语料（统一 5 字段）", False),
    ("│     └─ split_{train,val,test}.jsonl", "按场次 33/4/4 → 32377 / 4889 / 3110 条", False),
    ("└─ splits/", "③ 最终数据集层：8:1:1，seed=42", True),
    ("   ├─ yolo/images/{train,val,test}/", "检测主集：4316 / 346 / 380 张 @640×640", False),
    ("   ├─ yolo/labels/{train,val,test}/", "YOLO 归一化球员框（含 _aug0 增强副本）", False),
    ("   ├─ yolo/data.yaml", "类别与路径定义（实验 2 训练直接消费）", False),
    ("   ├─ texts/{train,val,test}.jsonl", "资讯背景语料：98 / 12 / 12 篇", False),
    ("   └─ split_summary.json", "划分明细统计", False),
    ("", "", False),
    ("src/basketball_dataset.py", "PyTorch Dataset 封装（实验 2 直接加载）", False),
    ("docs/", "DATA_CARD.md / PROVENANCE.md / CLEANUP_LOG.md", False),
]

TITLE = "最终数据集目录结构（三条数据线：视频 / 图像 / 解说文本）"

W, PAD, LH = 1560, 48, 42
H = PAD + 66 + LH * len(LINES) + 56 + PAD

img = Image.new("RGB", (W, H), "#FFFFFF")
d = ImageDraw.Draw(img)

# 标题栏
d.rectangle([0, 0, W, 96], fill="#1F3A5F")
d.text((PAD, 30), TITLE, font=F_TITLE, fill="#FFFFFF")

# 先算注释列起始 x（按最宽路径对齐）
colx = PAD + max(d.textlength(t, font=F_BOLD if b else F_TEXT) for t, _, b in LINES) + 56
colx = max(colx, 720)

y = 96 + 34
for text, note, bold in LINES:
    font = F_BOLD if bold else F_TEXT
    color = "#1F3A5F" if bold else "#24292F"
    if text:
        d.text((PAD, y), text, font=font, fill=color)
    if note:
        d.text((colx, y + 2), "# " + note, font=F_SMALL, fill="#6B7280")
    y += LH

# 页脚
d.line([(PAD, H - 58), (W - PAD, H - 58)], fill="#D0D7DE", width=2)
d.text((PAD, H - 44), "生成时间 2026-10-18 · 三条数据线划分均固定 seed=42，同源内容不跨集合", font=F_SMALL, fill="#6B7280")

img.save(OUT)
print(f"saved {OUT} ({img.width}x{img.height})")
