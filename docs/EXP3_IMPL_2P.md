# 实验 3 两人分工实施方案（可直接开工）

> 配套 `EXP3_PLAN.md`（总体方案）阅读。本文件回答两个问题：**每人具体写什么代码、跑什么命令**；**两人如何并行而不互相等待**。
> 分工原则：P1 = 精度线（把模型变小后精度守住），P2 = 速度线（把模型跑快并测准）。两条线只在"模型文件目录 + 结果 JSON"这一个接口上交汇。

---

## 一、分工总览

| | P1（精度线 / 模型侧） | P2（速度线 / 系统侧） |
|---|---|---|
| 负责任务 | 量化 3.1.1、蒸馏 3.1.3、误差分析、噪声测试 | 基线测量、推理加速 3.1.4、阶段 2 部署验证、infer.py |
| 主要产出 | INT8/FP16 模型文件、校准实验记录、蒸馏 best、分层误差数据 | bench_exp3.py、全版本速度/内存数据、TRT engine、端到端接口 |
| 主战场 | 本地 CPU（量化）+ Kaggle T4（蒸馏） | 本地 CPU（ORT/OpenVINO）+ Kaggle T4（TRT） |
| 报告章节 | 三.1 量化蒸馏部分、四 难点、五 误差分析 | 二 环境、三.2 加速部署、五 速度对比 |
| 合写 | 五 关联分析两段、一 目的、六 总结展望、七 参考文献 | |

**时序依赖只有一处**：P2 的基线（PyTorch FP32）必须最先跑出，P1 的量化对比要以它为锚点。P2 课前把基线做完，正式学时两人即完全并行。

---

## 二、接口契约（开工前 10 分钟先定这个）

### 1. 目录

```
exp3/
├── models/          # 所有导出产物，命名规范见下（P1 产出，P2 消费）
│   ├── a2_fp32.onnx
│   ├── a2_int8_val346.onnx
│   ├── a2_int8_train1000_pc.onnx     # 校准集_量化粒度 编进文件名
│   ├── a2_fp16.onnx
│   ├── a2_openvino_fp32/  a2_openvino_int8/
│   ├── a2_distilled.pt              # 蒸馏后学生
│   └── a2_trt_fp16.engine           # P2 在 Kaggle 产出
├── results/         # 每个"模型×后端"一个 JSON，schema 统一
├── scripts/
│   ├── export_quant.py      # P1
│   ├── eval_detail.py       # P1（分层 AP + 噪声）
│   ├── bench_exp3.py        # P2
│   ├── distill_yolo.py      # P1
│   └── infer.py             # P2
└── kaggle/          # 云端 notebook 副本
```

### 2. 结果 JSON 统一 schema（P2 定义，P1 遵守）

```json
{
  "model": "a2_int8_val346.onnx",
  "backend": "onnxruntime-cpu",        // pytorch / onnxruntime-cpu / openvino-cpu / tensorrt-t4
  "precision": "int8",                 // fp32 / fp16 / int8
  "hardware": "ryzen7-6800h-cpu",      // 或 kaggle-t4
  "size_mb": 6.1, "params_m": 3.2, "flops_g": 8.7,
  "lat_single_ms_p50": 95.0, "lat_single_ms_p95": 130.0,
  "lat_batch32_ms": 2100.0, "fps": 32.0,
  "map50": 0.412, "map50_95": 0.256,
  "ap_small": 0.30, "ap_medium": 0.45, "ap_large": 0.55,
  "noise_map50": 0.380, "mem_peak_mb": 850
}
```

两人脚本都往 `exp3/results/` 吐这个格式，最后 P2 一行 pandas 拼出报告主对比表——**全程不需要互相等**。

### 3. git 协作

`main` 只放契约（目录/schema）和汇总结果；P1 在 `quant-distill` 分支、P2 在 `bench-deploy` 分支开发，产物（模型文件不入库，.gitignore 掉，JSON 入库）合并回 main。

---

## 三、P2 实现细节（速度线）

### 1. bench_exp3.py —— 统一测速脚本（改造 `scripts/03_train/benchmark_models.py`）

四个后端做成同一接口 `predict_batch(imgs) -> boxes`，外层统一计分：

```python
# 计分口径（写死在脚本里，所有版本共用）
WARMUP, N_SINGLE, N_BATCH, BS = 10, 100, 20, 32

# 1) 预热 WARMUP 次 → 单样本计时 N_SINGLE 次 → p50/p95
# 2) 批 32 计时 N_BATCH 次 → 均值；吞吐 fps = BS / lat_batch32
# 3) psutil.Process().memory_info().rss 每 10 次采样取峰值（CPU 口径）
#    Kaggle GPU 口径换 torch.cuda.max_memory_allocated()
# 4) 循环 1000 次单样本，每 100 次记 RSS，检查波动 ≤5%（任务 3.1.5 稳定性指标）
```

各后端加载关键配置：

```python
# onnxruntime：任务书 3.1.4 要求的 ORT_ENABLE_ALL
import onnxruntime as ort
so = ort.SessionOptions()
so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
sess = ort.InferenceSession("exp3/models/a2_fp32.onnx", so,
                            providers=["CPUExecutionProvider"])

# openvino：LATENCY（单样本）与 THROUGHPUT（批量）两种提示各测一轮
from openvino.runtime import Core
core = Core()
ov_latency = core.compile_model("a2_openvino_fp32/a2.xml", "CPU",
                                {"PERFORMANCE_HINT": "LATENCY"})
```

注意事项：
- 导出统一加 `dynamic=True`（engine 除外），否则批 32 跑不了；
- CPU 测速时关掉后台大进程，两次运行取稳定值；
- mAP 不用自己算：`yolo val model=exp3/models/xxx.onnx data=data/splits/yolo/data.yaml split=test imgsz=640`，ultralytics 原生支持对导出格式做验证，结果抄进 JSON。

### 2. TensorRT（Kaggle T4，课外）

```bash
pip install tensorrt    # 装不上时退 onnxruntime-gpu（CUDA EP），见预案
yolo export model=exp3/models/a2_fp32.onnx format=engine half=True device=0 dynamic=True
yolo val model=a2_trt_fp16.engine data=... split=test     # 精度一致性
# bench_exp3.py 加 tensorrt 后端跑延迟/吞吐
```

### 3. infer.py —— 端到端 pipeline（给实验 4 的接口）

```
读图/BGR → letterbox 640×640 → 后端推理（构造时选 pt/onnx/ov/engine）→ NMS → 坐标还原 → JSON 框列表
```

交付形态：`from infer import Detector; det = Detector("a2_int8_val346.onnx"); det(img_bgr)`。这就是报告 3.2 节"部署验证"的可运行证据，也是实验 4 直接 import 的模块。

---

## 四、P1 实现细节（精度线）

### 1. 量化导出与校准实验矩阵（本方案的核心实验）

第一轮用 ultralytics 内置导出（简单、能跑通就先有数字）：

```bash
yolo export model=models/exp2/A2_yolov8n/weights/best.pt format=onnx imgsz=640 dynamic=True simplify=True          # FP32
yolo export model=models/exp2/A2_yolov8n/weights/best.pt format=onnx int8=True data=data/splits/yolo/data.yaml imgsz=640   # INT8（内置校准）
yolo export model=models/exp2/A2_yolov8n/weights/best.pt format=openvino int8=True data=data/splits/yolo/data.yaml         # OpenVINO 侧交叉对比
```

若 INT8 掉点 >2%，进入**校准实验矩阵**（这是报告难点章节的素材来源，每格数字都记录）：

| 实验 | 校准集 | 量化粒度 |
|---|---|---|
| E1 | val 346 张 | per-tensor |
| E2 | train 前 500 张 | per-tensor |
| E3 | train 前 1000 张 | per-tensor |
| E4 | train 前 1000 张 | **per-channel** |
| E5（兜底） | — | 退 FP16 |

E2-E4 需要自定义脚本 `export_quant.py`（ultralytics 内置的不开放校准集大小/粒度参数）：

```python
from onnxruntime.quantization import (quantize_static, CalibrationDataReader,
                                      QuantFormat, QuantType)

class YoloCalibReader(CalibrationDataReader):
    def __init__(self, img_paths, imgsz=640):
        self.imgs = iter([letterbox_bgr_to_nhwc(p, imgsz) for p in img_paths])
    def get_next(self):
        try:    return {"images": next(self.imgs)}     # 键名与 ONNX 输入名一致
        except StopIteration: return None

quantize_static("a2_fp32.onnx", out_name,
                YoloCalibReader(train_imgs[:N]),
                quant_format=QuantFormat.QDQ,
                weight_type=QuantType.QInt8,
                per_channel=(granularity == "pc"))
```

每个产物：跑 `yolo val` 记 mAP → 填入 JSON → 文件名即实验编号。全流程本地 CPU，每个导出约几分钟，**4 学时内能扫完整个矩阵**。

### 2. eval_detail.py —— 分层误差分析 + 噪声测试（报告要求 2 的"误差分布"）

- **分层 AP**：test 380 张的 GT 框按面积分三档（640×640 坐标系：<32² 小 / 32²~96² 中 / >96² 大，COCO 口径），对每档 GT 子集分别匹配预测算 AP50。实现：复用 `benchmark_models.py` 里的单类 mAP 匹配逻辑，只是按框大小过滤 GT。产出 FP32 vs INT8 的三档 AP 对比 → 验证"小目标量化误差更高"假设；
- **逐图 ΔAP 直方图**：每张图的 AP(FP32)−AP(INT8) 画分布，定位误差集中的图片（挑 2-3 张坏案例截图进报告）；
- **噪声测试**（任务 3.1.6 简化版）：预处理后对输入张量加 `torch.randn_like(x)*0.02` 高斯噪声，FP32 与 INT8 各测一轮 test mAP，对比降幅。

### 3. distill_yolo.py —— 蒸馏（改用 ultralytics 8.4 内置蒸馏，本地冒烟已通过）

> 原计划自写 KD 损失（继承 DetectionTrainer + adapter + hook）。实施时发现 ultralytics 8.4.176
> **原生支持知识蒸馏**（`nn/distill_model.py` + 训练参数 `distill_model`/`dis`），方案改为直接使用，
> `exp3/scripts/distill_yolo.py` 是锁定超参的薄封装。自定义方案保留在本节末尾备查。

- **内置实现**：总损失 = 学生 v8 检测损失（硬标签 box/cls/dfl）+ dis × 教师前景得分加权的
  neck/头特征 L2（P3/P4/P5 + Detect，MLP projector 自动对齐师生通道维度）；
  教师冻结 eval、no_grad；训练结束 fuse 自动剥离蒸馏包装，best.pt 即纯学生权重，可直接复用实验 3 量化/导出管线；
- **与任务书"0.3 硬 + 0.7 软标签 KL"口径的对应**：硬标签权重 1.0，软知识以特征蒸馏承载、由 dis 控制平衡；
  nc=1 单类下 logit-KL 信息量弱，前景加权特征蒸馏是检测蒸馏主流做法（FGD/LGD 一族），温度系数 T 不适用，
  报告按此口径说明；
- **已验证**：本地 CPU 冒烟（1 epoch × 2% 数据 × 480）跑通全流程，dis_loss 10.8→9.3 正常下降，
  best.pt 6.5MB 干净落地（产物在 `runs/detect/exp3/runs/a2_distill_smoke/`）；
- **Kaggle T4 正式训练**：`python exp3/scripts/distill_yolo.py --device 0 --epochs 12`（约 1-2 小时；
  消融可扫 `--dis 3/6/9`）；
- **超参口径**：lr0=0.002（实验 2 的 1/5，任务书要求）、epochs=12（任务书 10-15 区间）、
  batch=16、imgsz=640、cos_lr/seed=42/amp 全部对齐 A2 的 args.yaml；
- 达标判据：蒸馏版 test mAP50 ≥ 0.418（打平即合格），理想 0.42+ 逼近 v8m；不涨点就如实报告并分析边界
  （强预训练 + 4 千张数据下蒸馏收益有限），不算失败。

---

## 五、时间线（按人）

| 时段 | P1 | P2 |
|---|---|---|
| 课前（各 1-2h） | 验证 export 链路（FP32 ONNX 导出成功即算通）；写 `export_quant.py` 骨架 | **跑完 PyTorch FP32 基线**（延迟/吞吐/mAP/内存）→ `baseline.json` 定稿；bench 脚本支持 onnx |
| 学时 1-2 | INT8 首轮（E1）出 mAP；若掉点 >2% 启动矩阵 E2-E4，逐格记录 | FP32 ONNX + ORT ENABLE_ALL 测速；OpenVINO 导出与双模式测速 |
| 学时 3-4 | `eval_detail.py` 分层 AP + 噪声测试出数；打包 Kaggle 蒸馏任务并启动（异步跑） | 全版本 bench 跑完 → 主对比表初版；`infer.py` 联调 |
| 课外 1 | Kaggle 蒸馏 12 epoch（T4 约 1-2h），下载权重补测 | Kaggle TRT 导出 + GPU 侧测速（或 ORT-GPU 兜底） |
| 课外 2 | 写报告：三.1、四、五误差分析部分 | 写报告：二、三.2、五速度对比部分；主表与帕累托图成图 |
| 合并 | 两人合写关联分析两段 + 总结展望；按实际产出填分工表 | |

---

## 六、汇合检查点（只有两个）

1. **学时 2 结束**：P2 确认能评测 `exp3/models/` 下任意 P1 产物（格式通、数字出）——通不过则立即一起修接口，别拖到最后；
2. **课外 1 结束**：主对比表所有格子的数据来源 JSON 齐全，缺哪格补哪格。

其余时间两人零依赖，各自推进。
