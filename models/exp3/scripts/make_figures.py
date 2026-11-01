"""实验3 P1：报告插图生成（读取 exp3/results/*.json，输出到 exp3/results/figures/）.

图 1 量化主线总览（体积 + mAP50 双面板）
图 2 分层 AP 对比（量化误差集中在大目标的核心发现）
图 3 噪声鲁棒性（干净 vs σ=0.02 高斯噪声）
图 4 逐图 ΔAP 分布直方图
图 5 蒸馏主线（未蒸馏学生 / 蒸馏学生 / 教师：精度 + 体积双面板）

字号按任务书"图表中标题和文字字号均为五号"要求（约 10.5pt），dpi=300 直接可插入报告。
用法：python exp3/scripts/make_figures.py（PyCharm 右键 Run 或命令行均可，路径无关）
"""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RES = os.path.join(ROOT, "exp3/results")
OUT = os.path.join(RES, "figures")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["font.size"] = 10.5  # 五号

C_BASE, C_INT8, C_NOISE = "#4C72B0", "#DD8452", "#937860"  # 同族低饱和配色
C_DIST, C_TEACH = "#55A868", "#C44E52"  # 蒸馏学生 / 教师


def load(name):
    with open(os.path.join(RES, name), encoding="utf-8") as f:
        return json.load(f)


def clean_ax(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.3)


def fig1_quant_overview():
    rows = [("PyTorch FP32", 13.2, 0.419), ("INT8 E1\n(val校准)", 3.6, 0.420),
            ("INT8 E2\n(train500校准)", 3.5, 0.418), ("INT8 E4\n(per-channel)", 4.0, 0.418),
            ("蒸馏+INT8\n(val校准)", 3.5, 0.412)]
    names = [r[0] for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.6))
    a1.bar(names, [r[1] for r in rows], color=[C_BASE] + [C_INT8] * 3 + [C_DIST], width=0.62)
    for i, r in enumerate(rows):
        a1.text(i, r[1] + 0.25, f"{r[1]:.1f}", ha="center")
    a1.axhline(13.2, ls="--", lw=0.8, alpha=0.5)
    a1.annotate("体积 -72.9%", xy=(1, 3.6), xytext=(1.3, 8.5), color="white", fontsize=9,
                arrowprops=dict(arrowstyle="->", color="black", lw=0.8))
    a1.set_ylabel("模型体积 (MB)"); a1.set_title("(a) 模型体积"); clean_ax(a1)

    a2.bar(names, [r[2] for r in rows], color=[C_BASE] + [C_INT8] * 3 + [C_DIST], width=0.62)
    for i, r in enumerate(rows):
        a2.text(i, r[2] + 0.0005, f"{r[2]:.3f}", ha="center", fontsize=9)
    a2.axhline(0.419, ls="--", lw=0.8, alpha=0.5)
    a2.set_ylim(0.41, 0.425); a2.set_ylabel("mAP50 (test 380)"); a2.set_title("(b) 精度（基线 0.419）")
    clean_ax(a2)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig1_quant_overview.png"), dpi=300)
    plt.close(fig)


def fig2_layered_ap():
    d = load("eval_detail.json")
    groups = ["medium", "large"]
    labels = ["中目标 (n=3367)", "大目标 (n=208)"]
    fp32 = [d["fp32"][f"ap50_{g}"] for g in groups]
    int8 = [d["int8"][f"ap50_{g}"] for g in groups]
    x, w = [0, 1], 0.32
    fig, ax = plt.subplots(figsize=(6, 3.8))
    b1 = ax.bar([i - w / 2 for i in x], fp32, w, label="FP32", color=C_BASE)
    b2 = ax.bar([i + w / 2 for i in x], int8, w, label="INT8 (E1)", color=C_INT8)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.006, f"{b.get_height():.3f}",
                    ha="center", fontsize=9)
    for i, (a, b) in enumerate(zip(fp32, int8)):
        ax.annotate(f"Δ={b - a:+.3f}", xy=(i + w / 2, b + 0.03), ha="center", fontsize=9, color="#B04C4C")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_xlim(-0.6, 1.6)
    ax.set_ylabel("AP50"); ax.set_ylim(0, 0.48)
    ax.set_title("按目标尺寸分层的量化误差（test 380）")
    ax.text(0.02, 0.96, "注：小目标仅 3 框，无统计意义，未列出", transform=ax.transAxes,
            ha="left", va="top", fontsize=9, bbox=dict(boxstyle="round", fc="#F5F5F5", ec="none"))
    ax.legend(frameon=False); clean_ax(ax)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig2_layered_ap.png"), dpi=300)
    plt.close(fig)


def fig3_noise():
    d = load("eval_detail.json")
    bars = [("FP32 干净", d["fp32"]["map50"], C_BASE), ("FP32 +噪声", d["fp32_noise"]["map50"], C_BASE),
            ("INT8 干净", d["int8"]["map50"], C_INT8), ("INT8 +噪声", d["int8_noise"]["map50"], C_INT8)]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for i, (name, v, c, al) in enumerate(zip(
            [b[0] for b in bars], [b[1] for b in bars], [b[2] for b in bars], [1, 0.55, 1, 0.55])):
        ax.bar(i, v, color=c, alpha=al, width=0.58)
        ax.text(i, v + 0.0008, f"{v:.3f}", ha="center", fontsize=9)
    ax.set_xticks(range(4)); ax.set_xticklabels([b[0] for b in bars])
    ax.set_ylim(0.40, 0.425); ax.set_ylabel("mAP50 (test 380)")
    ax.set_title("噪声鲁棒性：σ=0.02 高斯噪声下两模型均基本无损")
    clean_ax(ax)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_noise.png"), dpi=300)
    plt.close(fig)


def fig4_delta_hist():
    d = load("eval_detail.json")["per_image_delta_ap"]
    edges = [round(-1 + 0.2 * i, 1) for i in range(11)]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.bar([f"{edges[i]:.1f}" for i in range(10)], d["hist"], width=0.8, color=C_BASE)
    ax.text(0.98, 0.95, f"均值 {d['mean']:+.3f}   标准差 {d['std']:.3f}\n最差 {d['min']:+.3f}   最好 {d['max']:+.3f}",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round", fc="#F5F5F5", ec="none"))
    ax.set_xlabel("逐图 ΔAP50 = AP(INT8) − AP(FP32)"); ax.set_ylabel("图片数")
    ax.set_title("量化影响非普遍性：380 张图 ΔAP 集中在 ±0.1 内，仅少数图波动")
    clean_ax(ax)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig4_delta_hist.png"), dpi=300)
    plt.close(fig)


def fig5_distill():
    rows = [("A2 学生\n(未蒸馏)", 0.419, 6.3), ("蒸馏\ndis=3", 0.420, 6.3),
            ("蒸馏\ndis=6", 0.418, 6.3), ("蒸馏\ndis=9", 0.422, 6.3),
            ("M1 教师\n(YOLOv8m)", 0.424, 50.0)]
    names = [r[0] for r in rows]
    colors = [C_BASE, C_DIST, C_DIST, C_DIST, C_TEACH]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.5, 3.6))
    a1.bar(names, [r[1] for r in rows], color=colors, width=0.62)
    for i, r in enumerate(rows):
        a1.text(i, r[1] + 0.0004, f"{r[1]:.3f}", ha="center", fontsize=9)
    a1.axhline(0.424, ls="--", lw=0.8, alpha=0.5)
    a1.set_ylim(0.413, 0.4265)
    a1.set_ylabel("mAP50 (test 380)")
    a1.set_title("(a) 蒸馏权重消融：dis=9 最优，超未蒸馏基线")
    clean_ax(a1)

    a2.bar(names, [r[2] for r in rows], color=colors, width=0.62)
    for i, r in enumerate(rows):
        a2.text(i, r[2] + 1.2, f"{r[2]:.1f}", ha="center", fontsize=9)
    a2.annotate("学生体积仅为教师 1/8（-87%）", xy=(2, 3.0), xytext=(1.2, 28), color="black", fontsize=9,
                arrowprops=dict(arrowstyle="->", color="black", lw=0.8))
    a2.set_ylabel("模型体积 (MB)")
    a2.set_title("(b) 体积：3.1M 参数 vs 教师 25.9M")
    clean_ax(a2)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig5_distill.png"), dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for fn in (fig1_quant_overview, fig2_layered_ap, fig3_noise, fig4_delta_hist, fig5_distill):
        fn()
        print("saved", fn.__name__, "->", os.path.join(OUT, fn.__name__.replace("fig", "fig").split("_")[0] + ".png"))
    print("all figures ->", OUT)
