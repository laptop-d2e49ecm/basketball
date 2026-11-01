# -*- coding: utf-8 -*-
"""图 3：视觉数据清洗机理解构图——"清洗到底改了什么"。

回答两个常见困惑（配报告第 3 条正文）：
1. 框不是画在图片上的：标注存在于同名 txt（数字坐标），训练时分别读取；
   "画框"只是给人看时的临时叠加渲染，原图像素不变；
2. 清洗不改内容，只改文件集合：代码里唯一的写操作是 shutil.move 成对移动
   （jpg+txt 一起搬进 quarantine/），本次 EXIF 重写命中 0 次。

面板：
(a) 一个真实样本的解剖：原图（未画框）| 标签 txt 实际内容 | 叠加显示（临时渲染）；
(b) 清洗前后目录状态对比（示意）：数量 4981 对 -> 2521 对，内容 0 字节改动。

用法：
    python scripts/05_evaluate/plot_fig3_mechanism.py
"""
from pathlib import Path

import cv2
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parents[2]
# 图像线暂存目录已按 CLEANUP_LOG 清理，样本改读标准化后的 splits/yolo（同一帧的 640 版本）
VISION = ROOT / "data" / "splits" / "yolo"
OUT = ROOT / "report" / "figures"

PT = 10.5              # 五号
FIG_W_IN = 14.5 / 2.54  # Word 版心宽
DPI = 300

plt.rcParams.update({
    "font.family": ["Times New Roman", "SimSun"],  # 西文 Times，中文回退宋体
    "axes.unicode_minus": False,
    "font.size": PT,
})

EXAMPLE = "v_-6Os86HzwCs_c001__f000005"  # 保留样本，10 个框
C_BOX = (180, 55, 55)   # 叠加框颜色（BGR）
C_CARD = "#F2F2F2"
C_EDGE = "#8C8C8C"
C_KEEP = "#4C72B0"
C_DROP = "#C44E52"


def load_example():
    img = cv2.imread(str(VISION / "images" / "test" / f"{EXAMPLE}.jpg"))
    label_path = VISION / "labels" / "test" / f"{EXAMPLE}.txt"
    lines = [l for l in label_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB), lines


def overlay_boxes(img_rgb, lines):
    """把 txt 坐标渲染成矩形（仅在内存副本上，用于展示）。"""
    im = img_rgb.copy()
    H, W = im.shape[:2]
    for line in lines:
        _cls, cx, cy, w, h = (float(v) for v in line.split())
        x1, y1 = int((cx - w / 2) * W), int((cy - h / 2) * H)
        x2, y2 = int((cx + w / 2) * W), int((cy + h / 2) * H)
        cv2.rectangle(im, (x1, y1), (x2, y2), C_BOX, 2)
    return im


def panel_a(fig, gs):
    img, lines = load_example()
    img_boxes = overlay_boxes(img, lines)

    ax1 = fig.add_subplot(gs[0])
    ax1.imshow(img)
    ax1.set_title("① 图像帧（像素不变）", fontsize=9.8)
    ax1.set_xlabel(f"{EXAMPLE}.jpg", fontsize=8.4)

    ax2 = fig.add_subplot(gs[1])
    ax2.axis("off")
    # 坐标仅保留 3 位小数用于展示，避免长数字行溢出面板
    show = [" ".join(v if i == 0 else f"{float(v):.3f}" for i, v in enumerate(l.split()))
            for l in lines[:8]]
    hidden = len(lines) - 8
    txt = "\n".join(show) + (f"\n……（共 {len(lines)} 行）" if hidden > 0 else "")
    ax2.text(0.04, 0.97, txt, transform=ax2.transAxes, va="top", ha="left",
             family=["Consolas", "SimSun"], fontsize=8.0, linespacing=1.5)
    ax2.set_title("② 同名 txt（框=数字）", fontsize=9.8)
    ax2.set_xlabel("每行：类别 cx cy w h\n（归一化；显示截断 3 位）", fontsize=7.6)

    ax3 = fig.add_subplot(gs[2])
    ax3.imshow(img_boxes)
    ax3.set_title("③ 叠加渲染（仅展示）", fontsize=9.8)
    ax3.set_xlabel("训练时分开读图与 txt，不生成本图", fontsize=8.4)

    for ax in (ax1, ax3):
        ax.set_xticks([])
        ax.set_yticks([])


def panel_b(fig, rect):
    ax = fig.add_axes(rect)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 3)
    ax.axis("off")

    def card(x, y, w, h, title, lines, title_color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08",
                                    fc=C_CARD, ec=C_EDGE, lw=0.8))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="center",
                color=title_color, fontweight="bold")
        body = "\n".join(lines)
        ax.text(x + 0.2, y + h - 0.75, body, va="top", ha="left",
                family=["Consolas", "SimSun"], fontsize=8.4, linespacing=1.7)

    card(0.3, 0.45, 3.4, 2.3, "清洗前", [
        "data/processed/vision/",
        "├─ images/   4981 个 .jpg",
        "├─ labels/   4981 个 .txt",
        "└─ quarantine/   （空）"], C_KEEP)
    card(6.3, 0.45, 3.4, 2.3, "清洗后", [
        "data/processed/vision/",
        "├─ images/   2521 个 .jpg",
        "├─ labels/   2521 个 .txt",
        "└─ quarantine/",
        "      2460 对近重复"], C_DROP)

    ax.add_patch(FancyArrowPatch((3.85, 1.75), (6.15, 1.75),
                                 arrowstyle="-|>", mutation_scale=14,
                                 color=C_DROP, lw=1.4))
    ax.text(5.0, 2.0, "clean_images.py", ha="center", va="bottom",
            fontweight="bold", fontsize=8.8)
    ax.text(5.0, 1.52, "唯一写操作：\nshutil.move\njpg+txt 成对隔离",
            ha="center", va="top", fontsize=8.6, linespacing=1.5)
    ax.text(5.0, 0.18, "图片像素与 txt 内容：0 字节改动（EXIF 重写命中 0 次；损坏 / 无效标注命中 0 个）",
            ha="center", va="center", fontsize=8.2, color="#555555")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(FIG_W_IN, 6.6), dpi=DPI)

    gs = fig.add_gridspec(1, 3, top=0.80, bottom=0.42, left=0.02, right=0.98,
                          wspace=0.08)
    fig.text(0.5, 0.955, "(a) 单个样本解剖：框不在图里，在同名 txt 里", ha="center", va="center")
    fig.text(0.5, 0.905, "(b) 清洗 = 只搬文件不改内容：成对移动近重复样本到隔离区", ha="center", va="center")
    panel_a(fig, gs)
    panel_b(fig, [0.02, 0.03, 0.96, 0.34])

    fig.savefig(OUT / "fig3_vision_clean_mechanism.png")
    plt.close(fig)
    print(f"[OK] {OUT / 'fig3_vision_clean_mechanism.png'}")


if __name__ == "__main__":
    main()
