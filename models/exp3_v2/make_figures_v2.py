# -*- coding: utf-8 -*-
"""实验3 v2 报告插图生成（数据源：models/exp3_v2/*.json + exp2_v2 eval json + 训练 results.csv）。

图1 量化主线总览（体积 + 各 INT8 版本相对自身 FP32 的 ΔmAP50 / ΔmAP50-95）
图2 分层 AP（各尺寸档 AP50 均无损）
图3 逐图 ΔAP 分布直方图（Δ = AP(INT8) − AP(FP32)）
图4 噪声鲁棒性
图5 蒸馏消融（强基座负结果，mAP50-95 为主指标）+ 体积
图6 蒸馏训练过程（val mAP50-95 + 蒸馏项）
图7 定性检测效果（A2′ 在 test 样例上的预测框）
figsize 宽度即报告中的插入宽度（FIG_W），文字按 1:1 印刷：标题/轴标签五号 10.5pt，刻度与数值 9pt。
输出：models/exp3_v2/figures/
"""
import csv
import glob
import json
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V2 = os.path.join(ROOT, "models/exp3_v2")
OUT = os.path.join(V2, "figures")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams.update({"font.size": 10.5, "axes.titlesize": 10.5, "axes.labelsize": 10.5,
                     "xtick.labelsize": 9, "ytick.labelsize": 9, "legend.fontsize": 9})

# 报告插入宽度（英寸），generate/refresh 脚本按同一宽度插图
FIG_W = {"fig1": 6.0, "fig2": 4.8, "fig3": 4.8, "fig4": 4.8, "fig5": 6.0, "fig6": 6.0, "fig7": 5.2}

C_BASE, C_INT8 = "#4C72B0", "#DD8452"
C_DIST, C_TEACH = "#55A868", "#C44E52"
C_DELTA = "#B04C4C"


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def clean_ax(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle="--", alpha=0.3)


QC = {r["name"]: r for r in load(os.path.join(V2, "quant_chain_v2.json"))["quant_chain"]}
BY = {r["name"]: r for r in load(os.path.join(ROOT, "models/exp2_v2/eval_test190.json"))["results"]}
DET = load(os.path.join(V2, "eval_detail_v2.json"))
MB = lambda rel: os.path.getsize(os.path.join(ROOT, rel)) / 1e6  # noqa: E731


def fig1_quant_overview():
    fp32 = QC["A2′ ONNX FP32"]
    vol = [("FP32", MB("models/exp3_v2/models/a2v2_fp32.onnx"), C_BASE),
           ("E1", MB("models/exp3_v2/models/a2v2_int8_val173.onnx"), C_INT8),
           ("E2", MB("models/exp3_v2/models/a2v2_int8_train500.onnx"), C_INT8),
           ("E4", MB("models/exp3_v2/models/a2v2_int8_val173_pc.onnx"), C_INT8),
           ("叠加", MB("models/exp3_v2/models/dis6v2_int8_val173.onnx"), C_DIST)]
    # 每个 INT8 版本相对"自身"FP32：E1/E2/E4 对 A2′ FP32，叠加对 dis6 FP32
    deltas = [("E1\nval173", QC["A2′ INT8 E1(val173)"], fp32),
              ("E2\ntrain500", QC["A2′ INT8 E2(train500)"], fp32),
              ("E4\nper-ch", QC["A2′ INT8 E4(per-ch)"], fp32),
              ("叠加\ndis6+E1", QC["dis6+INT8 叠加"], QC["dis6 ONNX FP32"])]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIG_W["fig1"], 2.9), gridspec_kw={"width_ratios": [1, 1.25]})
    a1.bar([v[0] for v in vol], [v[1] for v in vol], color=[v[2] for v in vol], width=0.62)
    for i, v in enumerate(vol):
        a1.text(i, v[1] + 0.3, f"{v[1]:.1f}", ha="center", fontsize=9)
    red = 1 - vol[1][1] / vol[0][1]
    a1.annotate("", xy=(1, vol[1][1] + 1.3), xytext=(0.25, vol[0][1] - 0.4),
                arrowprops=dict(arrowstyle="->", color="#333", lw=1.0))
    a1.text(1.15, 8.6, f"−{red * 100:.1f}%", fontsize=10.5, color="#333")
    a1.set_ylim(0, 15); a1.set_ylabel("模型体积 (MB)"); a1.set_title("(a) 体积"); clean_ax(a1)

    x = np.arange(len(deltas)); w = 0.36
    d50 = [(q["map50"] - b["map50"]) * 100 for _, q, b in deltas]
    d95 = [(q["map50_95"] - b["map50_95"]) * 100 for _, q, b in deltas]
    b1 = a2.bar(x - w / 2, d50, w, color=C_BASE, label="ΔmAP50")
    b2 = a2.bar(x + w / 2, d95, w, color=C_INT8, label="ΔmAP50-95")
    for bars in (b1, b2):
        for b in bars:
            v = b.get_height()
            a2.text(b.get_x() + b.get_width() / 2, v - 0.12, f"{v:+.2f}", ha="center", va="top", fontsize=8.5)
    a2.axhline(0, color="black", lw=0.8)
    a2.set_xticks(x); a2.set_xticklabels([d[0] for d in deltas])
    a2.set_ylim(-3.0, 0.9); a2.set_ylabel("相对 FP32 变化 (pp)")
    a2.set_title("(b) 代价：判定无损，定位约 −2pp")
    a2.legend(frameon=False, loc="upper center", ncol=2)  # 0 线以上为空白区，图例不压柱与数值
    clean_ax(a2)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig1_quant_overview.png"), dpi=300)
    plt.close(fig)


def fig2_layered_ap():
    groups = ["medium", "large"]
    labels = [f"中目标 (n={DET['fp32']['n_gt_medium']})", f"大目标 (n={DET['fp32']['n_gt_large']})"]
    fp32 = [DET["fp32"][f"ap50_{g}"] for g in groups]
    int8 = [DET["int8"][f"ap50_{g}"] for g in groups]
    x, w = np.arange(2), 0.32
    fig, ax = plt.subplots(figsize=(FIG_W["fig2"], 3.0))
    b1 = ax.bar(x - w / 2, fp32, w, label="FP32", color=C_BASE)
    b2 = ax.bar(x + w / 2, int8, w, label="INT8 (E1)", color=C_INT8)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.012, f"{b.get_height():.3f}",
                    ha="center", va="bottom", fontsize=9)
    for i, (a, b) in enumerate(zip(fp32, int8)):  # Δ 标在 1.0 网格线之上，避免被虚线穿过
        ax.text(i, 1.11, f"Δ={b - a:+.3f}", ha="center", va="bottom", fontsize=9, color=C_DELTA)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=10.5)
    ax.set_xlim(-0.6, 1.6); ax.set_ylabel("AP50"); ax.set_ylim(0, 1.34)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_xlabel("小目标仅 1 框，无统计意义，未列出", fontsize=9, color="#555")
    ax.set_title("分层 AP50：中、大目标均无损（test 190）")
    ax.legend(frameon=False, loc="upper left", ncol=2); clean_ax(ax)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig2_layered_ap.png"), dpi=300)
    plt.close(fig)


def fig3_delta_hist():
    d = DET["per_image_delta_ap"]
    vals = np.array(d["values"])
    edges = np.round(np.arange(-0.13, 0.1301, 0.02), 2)  # 中心箱 [-0.01, 0.01] 收纳 Δ=0
    cnt, _ = np.histogram(vals, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    fig, ax = plt.subplots(figsize=(FIG_W["fig3"], 3.0))
    ax.bar(centers, cnt, width=0.017, color=[C_INT8 if c < -0.005 else C_BASE for c in centers])
    for c, n in zip(centers, cnt):
        if n:
            ax.text(c, n + 2, str(n), ha="center", fontsize=8.5)
    ax.text(0.98, 0.95, f"不变（Δ=0）{d['n_unchanged']}/{d['n_images']} 张\n|Δ|≤0.05：{d['n_within_0.05']}/{d['n_images']} 张\n"
            f"均值 {d['mean']:+.4f}　标准差 {d['std']:.3f}",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round", fc="#F5F5F5", ec="none"))
    ax.set_xlabel("逐图 ΔAP50 = AP(INT8) − AP(FP32)"); ax.set_ylabel("图片数")
    ax.set_xlim(-0.14, 0.14); ax.set_ylim(0, max(cnt) * 1.18)
    ax.set_title("逐图 ΔAP50：量化影响非普遍（test 190）")
    clean_ax(ax)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_delta_hist.png"), dpi=300)
    plt.close(fig)


def fig4_noise():
    vals = [DET["fp32"]["map50"], DET["fp32_noise"]["map50"], DET["int8"]["map50"], DET["int8_noise"]["map50"]]
    names = ["FP32\n干净", "FP32\n+噪声", "INT8\n干净", "INT8\n+噪声"]
    fig, ax = plt.subplots(figsize=(FIG_W["fig4"], 3.0))
    for i, (v, c, al) in enumerate(zip(vals, [C_BASE, C_BASE, C_INT8, C_INT8], [1, 0.55, 1, 0.55])):
        ax.bar(i, v, color=c, alpha=al, width=0.58)
        ax.text(i, v + 0.0002, f"{v:.4f}", ha="center", fontsize=9)
    for i0 in (0, 2):
        dv = (vals[i0 + 1] - vals[i0]) * 100
        ax.text(i0 + 0.5, 0.9918, f"Δ={dv:+.2f}pp", ha="center", fontsize=9, color=C_DELTA)
    ax.set_xticks(range(4)); ax.set_xticklabels(names, fontsize=10.5)
    ax.set_ylim(0.985, 0.993); ax.set_ylabel("mAP50（纵轴截断）")
    ax.set_title("噪声鲁棒性：σ=0.02 高斯噪声下均基本无损")
    clean_ax(ax)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig4_noise.png"), dpi=300)
    plt.close(fig)


def fig5_distill():
    base, teach = BY["A2_yolov8n"], BY["A2_yolov8m"]
    rows = [("A2′\n基座", base, MB("models/exp2_v2/A2_yolov8n/weights/best.pt"), C_BASE),
            ("dis=3", BY["蒸馏dis3"], MB("models/exp3_v2/exp3-v3/a2v2_distill_dis3_best.pt"), C_DIST),
            ("dis=6", BY["蒸馏dis6"], MB("models/exp3_v2/exp3-v3/a2v2_distill_dis6_best.pt"), C_DIST),
            ("dis=9", BY["蒸馏dis9"], MB("models/exp3_v2/exp3-v3/a2v2_distill_dis9_best.pt"), C_DIST),
            ("M1′\n教师", teach, MB("models/exp2_v2/A2_yolov8m/weights/best.pt"), C_TEACH)]
    names = [r[0] for r in rows]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIG_W["fig5"], 2.9), gridspec_kw={"width_ratios": [1.35, 1]})
    a1.bar(names, [r[1]["map50_95"] for r in rows], color=[r[3] for r in rows], width=0.62)
    for i, r in enumerate(rows):
        a1.text(i, r[1]["map50_95"] + 0.0015, f"{r[1]['map50_95']:.4f}", ha="center", fontsize=8.5)
    a1.axhline(base["map50_95"], ls="--", lw=0.9, color="#555", alpha=0.7)
    a1.set_ylim(0.74, 0.80); a1.set_ylabel("mAP50-95 (test 190)")
    a1.set_title("(a) 三组蒸馏均未超过基座（虚线）")
    clean_ax(a1)
    a2.bar(names, [r[2] for r in rows], color=[r[3] for r in rows], width=0.62)
    for i, r in enumerate(rows):
        a2.text(i, r[2] + 1.0, f"{r[2]:.1f}", ha="center", fontsize=8.5)
    a2.set_ylim(0, 60); a2.set_ylabel("模型体积 (MB)"); a2.set_title("(b) 体积：学生为教师 1/8")
    clean_ax(a2)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig5_distill.png"), dpi=300)
    plt.close(fig)


def best_val(results_csv):
    rows = list(csv.DictReader(open(results_csv)))
    fit = [(float(r["metrics/mAP50(B)"]) + 9 * float(r["metrics/mAP50-95(B)"])) / 10 for r in rows]
    return float(rows[max(range(len(fit)), key=lambda i: fit[i])]["metrics/mAP50-95(B)"])


def fig6_curves():
    colors = {3: "#55A868", 6: "#4C72B0", 9: "#DD8452"}
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIG_W["fig6"], 2.9))
    for dis in (3, 6, 9):
        rows = list(csv.DictReader(open(os.path.join(V2, f"exp3-v3/a2v2_distill_dis{dis}_results.csv"))))
        xs = [int(r["epoch"]) for r in rows]
        a1.plot(xs, [float(r["metrics/mAP50-95(B)"]) for r in rows], marker="o", ms=2.5, lw=1.1,
                color=colors[dis], label=f"dis={dis}")
        a2.plot(xs, [float(r["train/dis_loss"]) / dis for r in rows], marker="o", ms=2.5, lw=1.1,
                color=colors[dis], label=f"dis={dis}")
    base_v = best_val(os.path.join(ROOT, "models/exp2_v2/A2_yolov8n/results.csv"))
    teach_v = best_val(os.path.join(ROOT, "models/exp2_v2/A2_yolov8m/results.csv"))
    a1.axhline(base_v, ls="--", lw=0.9, color="#555", alpha=0.8)
    a1.text(1, base_v + 0.0015, f"A2′ 基座 {base_v:.3f}", fontsize=8.5, color="#555")
    a1.axhline(teach_v, ls=":", lw=1.0, color=C_TEACH, alpha=0.9)
    a1.text(1, teach_v + 0.0015, f"M1′ 教师 {teach_v:.3f}", fontsize=8.5, color=C_TEACH)
    a1.set_xlabel("epoch"); a1.set_ylabel("val mAP50-95（173 张）")
    a1.set_ylim(0.755, teach_v + 0.012); a1.set_title("(a) 验证精度：回升至基座附近")
    a1.legend(frameon=False, loc="lower right", ncol=3, fontsize=8.5); clean_ax(a1)
    a2.set_xlabel("epoch"); a2.set_ylabel("蒸馏项 dis_loss / dis")
    a2.set_ylim(0, 1.2); a2.set_title("(b) 蒸馏项：无持续下降")
    clean_ax(a2)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig6_curves.png"), dpi=300)
    plt.close(fig)


def fig7_qualitative():
    from PIL import Image, ImageDraw, ImageFont
    from ultralytics import YOLO

    paths = sorted(glob.glob(os.path.join(ROOT, "data/splits/yolo/images/test/*.jpg")))[::47][:4]
    m = YOLO(os.path.join(ROOT, "models/exp2_v2/A2_yolov8n/weights/best.pt"))
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 34)
    tiles = []
    for p in paths:
        r = m.predict(p, conf=0.35, imgsz=640, device="cpu", verbose=False)[0]
        lbl = os.path.join(ROOT, "data/splits/yolo/labels/test", os.path.splitext(os.path.basename(p))[0] + ".txt")
        n_gt = sum(1 for line in open(lbl) if line.strip())
        img = Image.open(p).convert("RGB")
        d = ImageDraw.Draw(img)
        for b in r.boxes.xyxy.tolist():
            d.rectangle(b, outline=(40, 220, 40), width=3)
        tag = f"预测 {len(r.boxes)} 人 / 标注 {n_gt} 人"
        tw = d.textlength(tag, font=font)
        d.rectangle([0, 0, tw + 16, 46], fill=(0, 0, 0))
        d.text((8, 2), tag, fill=(255, 255, 255), font=font)
        tiles.append(img)
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * 2 + 8, h * 2 + 8), (255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 2) * (w + 8), (i // 2) * (h + 8)))
    sheet.save(os.path.join(OUT, "fig7_qualitative.jpg"), quality=90)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for fn in (fig1_quant_overview, fig2_layered_ap, fig3_delta_hist, fig4_noise,
               fig5_distill, fig6_curves, fig7_qualitative):
        fn()
        print("saved", fn.__name__)
    print("all ->", OUT)
