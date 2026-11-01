"""实验3 P1：M1(YOLOv8m) → A2(YOLOv8n) 知识蒸馏训练入口.

实现基于 ultralytics 8.4+ 内置 DistillationModel（无需自定义训练循环）：
- 硬标签：学生 v8 检测损失（box/cls/dfl，TaskAlignedAssigner）；
- 蒸馏项：教师前景得分加权的 neck/头特征 L2（P3/P4/P5 + Detect，MLP projector
  对齐师生通道维度），教师冻结 eval、no_grad；
- 总损失 = 硬标签 + dis × 蒸馏项，dis 为蒸馏权重（默认 6.0，可扫 3/6/9 做消融）；
- 训练结束 fuse 自动剥离蒸馏包装，best.pt 即纯学生权重，可直接量化/导出复用实验3管线。

与任务书"0.3 硬标签 + 0.7 软标签 KL"口径的对应关系（报告按此说明）：硬标签权重 1.0，
软知识以特征蒸馏承载并由 dis 控制平衡；nc=1 单类下 logit-KL 信息量弱，前景加权特征
蒸馏是检测蒸馏主流做法（FGD/LGD 一族），温度系数 T 不适用于特征 L2 范式。

用法（项目根目录）：
  本地 CPU 冒烟（验证管道通，约几分钟）：
    python exp3/scripts/distill_yolo.py --device cpu --epochs 1 --fraction 0.02 --imgsz 480 --batch 8
  Kaggle T4 正式训练（约 1-2 小时）：
    python exp3/scripts/distill_yolo.py --device 0 --epochs 12
"""
import argparse

from ultralytics import YOLO

TEACHER = "models/exp2/A2_yolov8m/weights/best.pt"  # M1 YOLOv8m（教师，mAP50 0.424）
STUDENT = "models/exp2/A2_yolov8n/weights/best.pt"  # A2 YOLOv8n（学生/初始化，mAP50 0.418）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", default=TEACHER)
    ap.add_argument("--student", default=STUDENT)
    ap.add_argument("--data", default="data/splits/yolo/data.yaml")
    ap.add_argument("--epochs", type=int, default=12)  # 任务书 10-15 epoch 区间
    ap.add_argument("--dis", type=float, default=6.0, help="蒸馏损失权重，消融可扫 3/6/9")
    ap.add_argument("--lr0", type=float, default=0.002, help="实验2 lr0=0.01 的 1/5（任务书口径）")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--fraction", type=float, default=1.0)
    ap.add_argument("--device", default="0")
    ap.add_argument("--name", default="a2_distill")
    a = ap.parse_args()

    YOLO(a.student).train(
        data=a.data,
        epochs=a.epochs,
        imgsz=a.imgsz,
        batch=a.batch,
        device=a.device,
        distill_model=a.teacher,  # 内置蒸馏：自动包装/冻结教师/训练后 fuse 剥离
        dis=a.dis,
        lr0=a.lr0,  # 其余超参对齐实验2 A2 args.yaml：cos_lr/seed/amp
        cos_lr=True,
        seed=42,
        amp=True,
        fraction=a.fraction,
        patience=a.epochs + 10,  # 12 epoch 完整跑完出曲线，不早停
        project="exp3/runs",
        name=a.name,
    )


if __name__ == "__main__":
    main()
