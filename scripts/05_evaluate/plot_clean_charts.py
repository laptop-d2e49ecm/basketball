# -*- coding: utf-8 -*-
"""生成"清洗前后质量指标对比"图表（报告第 3 条配图），数据全部读自各 clean_metrics.json。

模板格式要求："图表中标题和文字字号均为五号"。五号 = 10.5pt，因此：
1. 图内所有文字（含面板标题/刻度/图例/数值标签）统一 10.5pt；
2. 图幅宽度 = Word 版心宽度 14.5cm，插入 Word 时设置图片宽度为 14.5 厘米
   （不缩放），字号才保持五号不变；
3. 中文宋体、西文/数字 Times New Roman（与正文一致），通过字体回退列表实现。

输出（report/figures/）：
    fig1_vision_before_after.png  视觉数据清洗前后对比（瀑布图 + 指标对比 + 全流程）
    fig2_all_types_before_after.png  各数据线清洗前后总览（样本量 + 解说丢弃构成）

用法：
    python scripts/05_evaluate/plot_clean_charts.py
"""
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parents[2]
VISION = ROOT / "data" / "processed" / "vision"
OUT = ROOT / "report" / "figures"

# 五号 = 10.5pt；版心 14.5cm（A4 减去默认左右页边距）
PT = 10.5
FIG_W_IN = 14.5 / 2.54
DPI = 300

plt.rcParams.update({
    # family 用列表才启用逐字符字体回退：西文/数字命中 Times New Roman，中文回退宋体
    "font.family": ["Times New Roman", "SimSun"],
    "axes.unicode_minus": False,
    "font.size": PT,
    "axes.titlesize": PT,
    "axes.labelsize": PT,
    "xtick.labelsize": PT,
    "ytick.labelsize": PT,
    "legend.fontsize": PT,
})

C_KEEP = "#4C72B0"   # 蓝：保留/清洗前
C_DROP = "#C44E52"   # 红：剔除
C_FINAL = "#55A868"  # 绿：最终/清洗后
C_GRAY = "#8C8C8C"
C_AUG = "#DD8452"    # 橙：增强


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_boxes_after() -> int:
    """清洗后保留的标注框数 = 非增强标签文件的行数总和。
    图像线暂存目录（processed/vision/labels）已按 CLEANUP_LOG 清理，
    改读标准化产物 splits/yolo（同一批帧的标签，train/val/test 三侧合计）。"""
    total = 0
    labels_root = ROOT / "data" / "splits" / "yolo" / "labels"
    for split in ("train", "val", "test"):
        for p in (labels_root / split).glob("*.txt"):
            if "_aug" not in p.stem:
                total += len(p.read_text(encoding="utf-8").splitlines())
    return total


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linewidth=0.5, alpha=0.35)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.5)


def fig1_vision():
    metrics = load_json(VISION / "clean_metrics.json")
    manifest = load_json(VISION / "manifest.json")
    augment = load_json(VISION / "augment_log.json")
    split = load_json(ROOT / "data" / "splits" / "split_summary.json")["vision"]
    boxes_before = manifest["total_boxes"]
    boxes_after = clean_boxes_after()
    kept = metrics["kept"]

    fig = plt.figure(figsize=(FIG_W_IN, 4.9), dpi=DPI, layout="constrained")
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1.0])

    # (a) 瀑布图：清洗前后帧数变化归因
    ax = fig.add_subplot(gs[0, :])
    labels = ["清洗前\n（MOT 抽样后）", "近重复剔除", "损坏剔除", "标注无效剔除", "清洗后保留"]
    drops = [metrics["near_duplicates"], metrics["corrupt"], metrics["bad_labels"]]
    before = metrics["total"]
    after = kept
    xs = np.arange(5)
    levels = [before, after, after, after, after]  # 各阶段清洗后的水位
    ax.bar(xs[0], before, width=0.58, color=C_KEEP)
    for i, d in enumerate(drops, start=1):
        if d > 0:
            ax.bar(xs[i], d, bottom=levels[i], width=0.58, color=C_DROP)
            ax.text(xs[i], before + 120, f"\u2212{d}", ha="center", va="bottom")
        else:  # 检查过但未命中：画一条短横线标 0，体现清洗规则执行过
            ax.plot([xs[i] - 0.22, xs[i] + 0.22], [levels[i]] * 2, color=C_GRAY, lw=1.6)
            ax.text(xs[i], before + 120, "0", ha="center", va="bottom", color=C_GRAY)
    ax.bar(xs[4], after, width=0.58, color=C_FINAL)
    for x, v in ((0, before), (4, after)):
        ax.text(x, v + 120, str(v), ha="center", va="bottom")
    for x in range(4):  # 各柱间的水平虚线（水位线）
        ax.plot([x + 0.29, x + 1 - 0.29], [levels[x]] * 2,
                color=C_GRAY, lw=0.7, ls=(0, (3, 2)))
    ax.text(2, (before + after) / 2, f"冗余剔除 {metrics['near_duplicates'] / before:.1%}",
            ha="center", va="center", color=C_DROP)
    ax.set_xticks(xs, labels)
    ax.set_ylabel("帧数")
    ax.set_ylim(0, before * 1.16)
    ax.set_title("(a) 视觉数据清洗前后帧数归因（瀑布图）")
    style_axes(ax)

    # (b) 核心指标清洗前后对比（数量级跨度大，用对数轴 + 数值标签）
    ax = fig.add_subplot(gs[1, 0])
    cats = ["帧数\n(51%)", "标注框\n(49%)", "序列数\n(100%)"]
    before_v = [before, boxes_before, manifest["sequences"]]
    after_v = [after, boxes_after, len(load_json(VISION / "manifest.json")["detail"])]
    xs = np.arange(3)
    w = 0.36
    b1 = ax.bar(xs - w / 2, before_v, w, color=C_KEEP, label="清洗前")
    b2 = ax.bar(xs + w / 2, after_v, w, color=C_FINAL, label="清洗后")
    ax.set_yscale("log")
    ax.set_ylim(10, 2e6)
    for bars in (b1, b2):
        for r in bars:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() * 1.15,
                    f"{r.get_height():.0f}", ha="center", va="bottom", fontsize=PT)
    ax.set_xticks(xs, cats)
    ax.set_ylabel("数量（对数刻度）")
    ax.set_title("(b) 核心指标清洗前后对比")
    ax.legend(ncol=2, frameon=False, loc="upper left")
    style_axes(ax)

    # (c) 处理全流程样本量变化（横向条形，类别名水平排布不碰撞）
    ax = fig.add_subplot(gs[1, 1])
    stages = ["MOT 抽样后", "清洗后", "增强后", "训练集", "验证集", "测试集"]
    vals = [before, after, after + augment["augmented_images"],
            split["images"]["train"], split["images"]["val"], split["images"]["test"]]
    colors = [C_KEEP, C_FINAL, C_AUG, C_GRAY, C_GRAY, C_GRAY]
    ys = np.arange(len(stages))
    ax.barh(ys, vals, height=0.62, color=colors)
    for y, v in zip(ys, vals):
        ax.text(v + 120, y, str(v), va="center")
    ax.set_yticks(ys, stages)
    ax.invert_yaxis()
    ax.set_xlabel("帧数")
    ax.set_xlim(0, max(vals) * 1.2)
    ax.set_title("(c) 清洗—增强—划分全流程样本量")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linewidth=0.5, alpha=0.35)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.5)

    fig.savefig(OUT / "fig1_vision_before_after.png")
    plt.close(fig)


def fig2_all_types():
    """各数据线清洗前后总览（2026-10-13 方案 v4：结构化线已删除，见 docs/CLEANUP_LOG.md #7）。
    (a) 现存四条数据线的样本量对比；(b) 解说语料清洗丢弃构成（量最大的文本线）。"""
    multisports_m = load_json(ROOT / "data" / "processed" / "multisports" / "clean_metrics.json")
    vision_m = load_json(VISION / "clean_metrics.json")
    livetext_m = load_json(ROOT / "data" / "processed" / "texts" / "livetext" / "clean_metrics.json")
    text_m = load_json(ROOT / "data" / "processed" / "texts" / "clean_metrics.json")

    fig = plt.figure(figsize=(FIG_W_IN, 2.75), dpi=DPI, layout="constrained")

    # (a) 各数据线样本量清洗前后对比（量级 122 ~ 4.1 万，用对数横轴）
    ax = fig.add_subplot(1, 2, 1)
    rows = [  # (显示名, 清洗前, 清洗后)
        ("视频·段", multisports_m["videos_before"], multisports_m["videos_after"]),
        ("图像·帧", vision_m["total"], vision_m["kept"]),
        ("解说·条", livetext_m["entries_before"], livetext_m["entries_after"]),
        # 资讯清洗后 120 篇为 Data-Juicer 流水线输出（手工线 json kept=122），见 docs/PROVENANCE.md
        ("资讯·篇", text_m["total"], 120),
    ]
    rows.sort(key=lambda r: r[1])
    names = [r[0] for r in rows]
    b = np.array([r[1] for r in rows], dtype=float)
    a = np.array([r[2] for r in rows], dtype=float)
    ys = np.arange(len(rows))
    h = 0.36
    ax.barh(ys - h / 2, b, h, color=C_KEEP, label="清洗前")
    ax.barh(ys + h / 2, a, h, color=C_FINAL, label="清洗后")
    ax.set_xscale("log")
    ax.set_xlim(50, 3e5)
    for y, (bv, av) in enumerate(zip(b, a)):
        ax.text(bv * 1.15, y - h / 2, f"{bv:,.0f}", va="center")
        ax.text(av * 1.15, y + h / 2, f"{av:,.0f}", va="center")
    ax.set_yticks(ys, names)
    ax.set_xlabel("样本量（段 / 帧 / 条 / 篇，对数刻度）")
    ax.set_title("(a) 各数据线清洗前后样本量")
    ax.legend(ncol=2, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.28))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linewidth=0.5, alpha=0.35)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.5)

    # (b) 解说语料清洗丢弃构成（横向条形，数值标签标注）
    ax = fig.add_subplot(1, 2, 2)
    drops = livetext_m["entries_dropped"]
    order = [("去空行", drops["empty"]), ("超短行", drops["too_short"]),
             ("重复记录", drops["duplicate"]), ("无有效文字", drops["no_word"])]
    names_d = [o[0] for o in order]
    vals_d = [o[1] for o in order]
    ys = np.arange(len(order))
    ax.barh(ys, vals_d, height=0.55, color=C_DROP)
    for y, v in zip(ys, vals_d):
        ax.text(v + 6, y, str(v), va="center")
    total_drop = sum(vals_d)
    ax.text(0.97, 0.25,
            f"共剔除 {total_drop} 条\n（{livetext_m['entries_before']:,} → {livetext_m['entries_after']:,}）",
            transform=ax.transAxes, ha="right", va="center", color=C_FINAL)
    ax.set_yticks(ys, names_d)
    ax.invert_yaxis()
    ax.set_xlabel("丢弃条数")
    ax.set_xlim(0, max(vals_d) * 1.25)
    ax.set_title("(b) 解说语料清洗丢弃构成")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="x", linewidth=0.5, alpha=0.35)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.5)

    fig.savefig(OUT / "fig2_all_types_before_after.png")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fig1_vision()
    fig2_all_types()
    for p in sorted(OUT.glob("*.png")):
        print(f"[OK] {p}")


if __name__ == "__main__":
    main()
