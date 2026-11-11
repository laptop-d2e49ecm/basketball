# -*- coding: utf-8 -*-
"""生成“实验1→实验5 全流程闭环与数据流”示意图（图 1-1）。

用法：python report/make_loop_figure.py
输出：report/figures/fig1_loop.png（300 dpi，供 docx 以 14 cm 宽插入）
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "report" / "figures" / "fig1_loop.png"

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

FILL = "#E9EFF7"
EDGE = "#2F4B6E"
ACCENT = "#8C4A3F"

STAGES = [
    ("实验 1", "数据采集", ["526 段视频", "5,042 帧检测", "40,376 条解说"]),
    ("实验 2", "模型训练", ["mAP50 0.992", "A1/A2/M1 对比", "云端 T4 训练"]),
    ("实验 3", "算法优化", ["INT8 3.5 MB", "体积 -72.5%", "蒸馏 dis=6"]),
    ("实验 4", "前后端系统", ["12 个 API", "/api/v1 统一", "五页 + 视频页"]),
    ("实验 5", "Agent 部署", ["5 个工具", "LoRA 94.2%", "端到端 2.2 s"]),
]

FLOW = ["8:1:1 划分", "best.pt", "INT8 ONNX", "统一信封"]


def main() -> int:
    fig, ax = plt.subplots(figsize=(7.4, 3.3), dpi=300)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    n = len(STAGES)
    w, gap = 0.165, 0.030
    left = 0.5 - (n * w + (n - 1) * gap) / 2
    y0, h = 0.46, 0.40

    for i, (tag, name, lines) in enumerate(STAGES):
        x = left + i * (w + gap)
        ax.add_patch(FancyBboxPatch(
            (x, y0), w, h, boxstyle="round,pad=0.005,rounding_size=0.010",
            linewidth=1.0, edgecolor=EDGE, facecolor=FILL, zorder=2))
        ax.text(x + w / 2, y0 + h - 0.042, tag, ha="center", va="center",
                fontsize=8.4, color=ACCENT, zorder=3)
        ax.text(x + w / 2, y0 + h - 0.100, name, ha="center", va="center",
                fontsize=9.4, color="#1F3552", zorder=3)
        for j, line in enumerate(lines):
            ax.text(x + w / 2, y0 + h - 0.172 - j * 0.070, line, ha="center",
                    va="center", fontsize=7.4, color="#33475B", zorder=3)

        if i < n - 1:
            xs, xe = x + w + 0.002, x + w + gap - 0.002
            ax.add_patch(FancyArrowPatch((xs, y0 + h / 2), (xe, y0 + h / 2),
                                         arrowstyle="-|>", mutation_scale=8,
                                         linewidth=0.9, color=EDGE, zorder=4))
            ax.text((xs + xe) / 2, y0 - 0.035, FLOW[i], ha="center",
                    va="center", fontsize=6.2, color="#5A6B7D", zorder=3)

    ax.add_patch(FancyBboxPatch(
        (left, 0.09), n * w + (n - 1) * gap, 0.25,
        boxstyle="round,pad=0.005,rounding_size=0.010",
        linewidth=0.9, edgecolor="#9AA9B8", facecolor="#FAFBFD",
        linestyle=(0, (4, 2)), zorder=2))
    ax.text(left + 0.010, 0.300, "四组复用点", ha="left", va="center",
            fontsize=7.6, color="#1F3552", zorder=3)
    ax.text(left + 0.010, 0.212,
            "① LoRA 思路（实验2 → 实验5）　② 量化策略（实验3 → 实验5）",
            ha="left", va="center", fontsize=6.8, color="#33475B", zorder=3)
    ax.text(left + 0.010, 0.150,
            "③ 统一信封/错误码（实验4 → 实验5）　④ 数据集（实验1 → 2/3/4/5）",
            ha="left", va="center", fontsize=6.8, color="#33475B", zorder=3)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # 去掉四周白边，让图形在 15 cm 宽度里尽量大
    from PIL import Image, ImageChops

    im = Image.open(OUT).convert("RGB")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im, bg)
    box = diff.getbbox()
    if box:
        pad = 6
        box = (max(0, box[0] - pad), max(0, box[1] - pad),
               min(im.width, box[2] + pad), min(im.height, box[3] + pad))
        im.crop(box).save(OUT)
    print(f"生成 {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
