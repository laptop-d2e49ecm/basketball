# -*- coding: utf-8 -*-
"""实验 2：训练篮球球员检测模型（YOLOv8）。

实验组（任务书要求：不同规模对比 + 消融验证数据增强收益）：
    A1  yolov8n + 原始帧 2158         （data_ablation.yaml）
    A2  yolov8n + 原始+增强 4316      （data.yaml，正式数据集）
    B1  yolov8s + 原始帧 2158         （可选，时间紧可砍）
    B2  yolov8s + 原始+增强 4316      （冲最高精度）
    M1  yolov8m + 原始+增强 4316      （容量上限探索组，batch=8，报告"模型容量探索"用）
    C1/C2/D1                           （YOLO11n/11s/v5n 代际对比，选做）

对应任务书（docs/实验2任务书.pdf）四阶段：
    阶段 2.1 环境部署   —— Colab/AutoDL 自带 CUDA+PyTorch；本地 CPU 冒烟即 2.1.3 数据关联验证；
    阶段 2.2 模型选型   —— 实验 1 数据为逐球员框标注（YOLO 格式），唯一匹配任务是检测而非分类，
                           选 ultralytics YOLOv8（n/s/m 规模梯度对比），预训练权重 ImageNet/COCO 迁移；
    阶段 2.3 训练优化   —— AMP 混合精度（amp=True 自动）、早停（patience，默认 30）、
                           余弦学习率调度（cos_lr）、梯度累积（accumulate，小显存卡用）；
    阶段 2.4 适配（选做）—— 小样本侧 LoRA 等留实验 5（解说语料微调）完成。

用法：
    本地冒烟（CPU，验管道）：
        python scripts/03_train/train_yolo.py --run A2 --epochs 1 --fraction 0.05 --imgsz 480
    正式训练（Colab T4 / AutoDL，GPU）：
        python scripts/03_train/train_yolo.py --run all          # 依次全跑
    正式训练（Kaggle，数据集以只读 Dataset 挂载）：
        python scripts/03_train/train_yolo.py --run A1,A2,M1 --epochs 50 --patience 15 \
            --data-root /kaggle/input/<数据集名> --work-dir /kaggle/working --device 0
        # --data-root 指向含 images/ labels/ 的数据根；清单与 yaml 自动生成到 --work-dir，
        # 结果输出 <work-dir>/exp2/，训完打包下载（Kaggle 关机即清空 working）
    结果都在 models/exp2/<run 名>/，交 best.pt + results.csv 即可写报告。

说明：
    - 首次运行自动下载 yolov8n/v8s/v8m 等官方预训练权重（COCO）；
    - 超参固定 seed=42 保证可复现，报告里照抄 args.yaml 即是超参表；
    - 训练完自动在 test 集跑一次评估（split='test'），产出最终 mAP。
"""
import argparse
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[2]  # 项目根

RUNS = {
    "A1": {"model": "yolov8n.pt", "data": "data/splits/yolo/data_ablation.yaml"},
    "A2": {"model": "yolov8n.pt", "data": "data/splits/yolo/data.yaml"},
    "B1": {"model": "yolov8s.pt", "data": "data/splits/yolo/data_ablation.yaml"},
    "B2": {"model": "yolov8s.pt", "data": "data/splits/yolo/data.yaml"},
    # M1：模型容量上限探索（同 A2 数据只换 v8m；25M 参数 batch 降到 8 防 OOM）
    "M1": {"model": "yolov8m.pt", "data": "data/splits/yolo/data.yaml", "batch": 8},
    # C/D 组：YOLO 系列代际对比（同数据同超参，只换模型），选型实证用
    "C1": {"model": "yolo11n.pt", "data": "data/splits/yolo/data.yaml"},
    "C2": {"model": "yolo11s.pt", "data": "data/splits/yolo/data.yaml"},
    "D1": {"model": "yolov5n.pt", "data": "data/splits/yolo/data.yaml"},
}


def ensure_ablation_list() -> None:
    """生成"仅原始帧"训练清单（绝对路径，换机器重跑自动适配）。

    ultralytics 对 txt 清单里的相对路径按运行目录解析，标签会配不上，
    因此清单必须写绝对路径，且每次训练前在本机重新生成。
    """
    img_dir = ROOT / "data/splits/yolo/images/train"
    lines = [str(p.resolve()) for p in sorted(img_dir.glob("*.jpg"))
             if not p.name.endswith("_aug0.jpg")]
    out = ROOT / "data/splits/yolo/original_train.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ablation] 原始帧清单 {len(lines)} 张 -> {out}")


def adapt_readonly_root(data_root: Path, work_dir: Path) -> dict[str, str]:
    """只读数据挂载适配（Kaggle /kaggle/input 等，实验报告"云端数据路径动态适配"的仓库版）。

    挂载目录只读导致 ultralytics 无法写 .cache、仓库内相对路径的 yaml 失效；
    在可写 work_dir 下重新生成绝对路径清单与 yaml，val/test 仍用挂载内相对路径。
    返回 {仓库内 data 路径: 云端生成 yaml 绝对路径}，train_one 据此替换。
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    img_dir = data_root / "images/train"
    lines = [str(p) for p in sorted(img_dir.glob("*.jpg"))
             if not p.name.endswith("_aug0.jpg")]
    txt = work_dir / "original_train_cloud.txt"
    txt.write_text("\n".join(lines), encoding="utf-8")
    print(f"[cloud] 原始帧清单 {len(lines)} 张 -> {txt}")

    def make_yaml(name: str, train: str) -> Path:
        yml = work_dir / name
        yml.write_text(
            f"# 自动生成（只读挂载适配），勿手改\n"
            f"path: {data_root}\ntrain: {train}\n"
            f"val: images/val\ntest: images/test\n\nnames:\n  0: player\n",
            encoding="utf-8")
        return yml

    return {
        "data/splits/yolo/data.yaml": str(make_yaml("data_cloud.yaml", "images/train")),
        "data/splits/yolo/data_ablation.yaml": str(make_yaml("data_ablation_cloud.yaml", str(txt))),
    }


def train_one(run: str, epochs: int, imgsz: int, batch: int, fraction: float,
              device: str | None, patience: int, cos_lr: bool,
              data_map: dict[str, str] | None = None, out_root: Path | None = None) -> None:
    cfg = RUNS[run]
    out_root = out_root or (ROOT / "models/exp2")
    run_dir = out_root / f"{run}_{cfg['model'].split('.')[0]}"
    marker = run_dir / "done.marker"
    if marker.exists():  # 断线重跑：已完整训练+终评的组直接跳过
        print(f"[{run}] 已存在完成标记 {marker}，跳过（删除该文件可强制重训）")
        return
    data = (data_map or {}).get(cfg["data"], str(ROOT / cfg["data"]))
    if "ablation" in cfg["data"] and data_map is None:
        ensure_ablation_list()  # 云端适配时 adapt_readonly_root 已生成清单
    model = YOLO(cfg["model"])
    extra = {"fraction": fraction} if fraction < 1.0 else {}
    model.train(
        data=data,
        epochs=epochs, imgsz=imgsz, batch=cfg.get("batch", batch),
        device=device, seed=42, project=str(out_root),
        name=f"{run}_{cfg['model'].split('.')[0]}", exist_ok=True,
        patience=patience,      # 任务书 2.3.2 早停（默认 30 epoch 无提升即停）
        cos_lr=cos_lr,          # 任务书 2.3.2 学习率调度（余弦退火）
        # amp 混合精度默认开启（amp=True，任务书 2.3.1 第 1 条）；
        # 梯度累积由 ultralytics 的 nbs=64 机制自动完成（batch 16 → 隐式累积 4 步，任务书 2.3.1 第 2 条）
        **extra,
    )
    # test 集终评（冒烟跑 1 epoch 时也执行，量小不耗时）
    metrics = model.val(split="test", project=str(out_root),
                        name=f"{run}_test", exist_ok=True)
    print(f"[{run}] test mAP50={metrics.box.map50:.4f}  mAP50-95={metrics.box.map:.4f}")
    marker.write_text(
        f"mAP50={metrics.box.map50:.4f}\nmAP50-95={metrics.box.map:.4f}\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="实验 2 YOLO 训练入口")
    parser.add_argument("--run", default="A2",
                        help="A1/A2/B1/B2/M1/C1/C2/D1 或 all（依次全跑）")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16,
                        help="默认批次；RUNS 里带 batch 的组（如 M1=8）自动覆盖")
    parser.add_argument("--fraction", type=float, default=1.0,
                        help="<1.0 时只采样该比例训练（冒烟用）")
    parser.add_argument("--device", default=None, help="cpu / 0（GPU）/ 空=自动")
    parser.add_argument("--patience", type=int, default=30,
                        help="早停轮数（任务书 2.3.2；冒烟时建议 --patience 5）")
    parser.add_argument("--no-cos-lr", action="store_true",
                        help="关闭余弦学习率调度（默认开）")
    parser.add_argument("--data-root", default=None,
                        help="只读数据挂载根（Kaggle 等，指向含 images/ labels/ 的目录）；"
                             "给出后在 --work-dir 重新生成清单与 yaml")
    parser.add_argument("--work-dir", default=None,
                        help="可写输出目录（Kaggle 用 /kaggle/working）；清单、yaml 与训练结果都写这里")
    args = parser.parse_args()

    data_map, out_root = None, None
    if args.data_root:
        work_dir = Path(args.work_dir) if args.work_dir else Path("cloud_work")
        data_map = adapt_readonly_root(Path(args.data_root), work_dir)
        out_root = work_dir / "exp2"
    elif args.work_dir:
        out_root = Path(args.work_dir) / "exp2"
    elif Path("/kaggle/input").exists():
        print("[提示] 检测到 Kaggle 环境：请加 --data-root /kaggle/input/<数据集名> "
              "--work-dir /kaggle/working")

    runs = list(RUNS) if args.run == "all" else args.run.split(",")
    for run in runs:
        print(f"\n===== RUN {run} =====")
        train_one(run.strip(), args.epochs, args.imgsz, args.batch,
                  args.fraction, args.device, args.patience,
                  not args.no_cos_lr, data_map, out_root)


if __name__ == "__main__":
    main()
