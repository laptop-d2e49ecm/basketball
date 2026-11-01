# 实验 3 交接包：P1 精度线成果 → P2 速度线整合

> 打包时间：2026-10-28。P1（精度线：量化 / 蒸馏 / 误差分析）已全部完成并落盘，
> 本包含 P2 补测速度、整合最终报告所需的全部产物。
> 接口契约与实现细节见 `docs/EXP3_IMPL_2P.md`（P2 实现细节在其第三节，已到命令级）。

## 一、包内容清单

| 目录 | 内容 | 说明 |
|---|---|---|
| `models/` | 10 个模型文件（共 64MB） | P2 测速对象；命名 = 模型_校准集[_粒度] |
| `results/` | 9 个结果 JSON + `figures/` 5 张图 | 统一 schema；速度字段全为 null——**最终未回填**，速度以 P2 交付实测与合并稿表5/6/7 为准（见三.2、七） |
| `scripts/` | export_quant / eval_detail / distill_yolo / make_figures | 精度线全流程可复现 |
| `runs_distill/` | 3 组蒸馏训练记录（dis=3/6/9） | results.csv、训练曲线、val 预测图；**weights 已剔除**（成品权重在 `models/`），冒烟组未打包 |
| `report/实验3报告/` |  
| `docs/` | EXP3_PLAN / EXP3_IMPL_2P / EXP3_KAGGLE_STEPS | 方案、分工契约、云端操作手册 |
| `data/data.yaml` | 数据集配置 | `yolo val` 命令要用；图片在仓库 `data/splits/yolo/`（本包不含图片） |

## 二、主对比表（P1→P2 交接快照：精度列定稿，速度列为待测占位，未回填）

| 模型文件 | 后端 | 精度 | 体积(MB) | mAP50 | mAP50-95 | CPU延迟p50/p95(ms) | 批32(ms) | FPS | 内存峰值(MB) |
|---|---|---|---|---|---|---|---|---|---|
| a2.pt | pytorch | fp32 | 6.5 | 0.419 | 0.245 | 待测 | 待测 | 待测 | 待测 |
| a2_fp32.onnx | onnxruntime-cpu | fp32 | 13.2 | 0.419 | 0.245 | 待测 | 待测 | 待测 | 待测 |
| **a2_int8_val346.onnx**（E1，部署推荐） | onnxruntime-cpu | int8 | 3.6 | 0.420 | 0.246 | 待测 | 待测 | 待测 | 待测 |
| a2_int8_train500.onnx（E2） | onnxruntime-cpu | int8 | 3.5 | 0.418 | 0.240 | 待测 | 待测 | 待测 | 待测 |
| a2_int8_val346_pc.onnx（E4） | onnxruntime-cpu | int8 | 4.0 | 0.418 | 0.243 | 待测 | 待测 | 待测 | 待测 |
| a2_distill_dis3.pt | pytorch | fp32 | 6.3 | 0.420 | 0.246 | 待测 | 待测 | 待测 | 待测 |
| a2_distilled.pt（dis=6 主跑） | pytorch | fp32 | 6.3 | 0.418 | 0.245 | 待测 | 待测 | 待测 | 待测 |
| **a2_distill_dis9.pt**（蒸馏最优） | pytorch | fp32 | 6.3 | 0.422 | 0.247 | 待测 | 待测 | 待测 | 待测 |
| a2_distilled_int8.onnx（蒸馏+量化） | onnxruntime-cpu | int8 | 3.5 | 0.412 | 0.240 | 待测 | 待测 | 待测 | 待测 |
| （P2 新增）openvino fp32 / int8 | openvino-cpu | — | — | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| （P2 新增，选做）trt fp16 | tensorrt-t4 | fp16 | — | 待测 | 待测 | — | — | 待测 | 待测 |

注：a2.pt 体积 6.5MB 系 PyTorch 半精度存储；速度对比的体积基准以 ONNX FP32 13.2MB 为准。

## 三、P2 待办清单（2026-10-28 下发，2026-10-30 全部关闭）

下发时的原始要求保留如下，每项以 → 标注实际完成情况与产物位置：

1. **bench_exp3.py 统一测速**（口径写死，全版本共用）：WARMUP=10 预热 → 单样本 100 次取 p50/p95 → 批 32 跑 20 次取均值 → fps = 32 / 批延迟；ORT 开 `ORT_ENABLE_ALL`；OpenVINO 分 LATENCY / THROUGHPUT 两种 hint 各测一轮。
   → ✅ 完成：GPU 线 `exp3/p2_delivery/gpu/scripts/bench_exp3.py`、CPU 线 `exp3/p2_delivery/scripts/`，计时口径与下发一致（预热 10 / 单图 100 / 批 20 + CUDA 同步）；实测记录在 `exp3/p2_delivery/results/`（含两轮独立复测）。
2. **回填 JSON**：把 `lat_single_ms_p50`、`lat_single_ms_p95`、`lat_batch32_ms`、`fps`、`mem_peak_mb` 五个 null 字段填进 `results/` 对应文件（schema 见 EXP3_IMPL_2P.md 第二节，勿改其它字段）。
   → ⚠️ 关闭方式变更：P1 的 `exp3/results/*.json` 速度字段未回填（保持 null，见第一节与第七节说明）；最终速度数字以 P2 交付实测 `exp3/p2_delivery/results/md_comparison.csv`、`md_summary.json` 及合并稿表5/表6/表7 为准。
3. **OpenVINO 双档**：`yolo export format=openvino`（FP32）+ `int8=True`（NNCF）导出、测速、跑 mAP；新产物按命名规范入 `models/`、新 JSON 入 `results/`。
   → ✅ 完成：OpenVINO FP32 线程调优版（CPU 最终推荐）与 INT8 / DFL-FP32 变体、LATENCY / THROUGHPUT 双 hint 全测（`exp3/p2_delivery/results/bench_a2_openvino_*.json`）。
4. **TensorRT FP16（选做）**：Kaggle T4 `format=engine half=True`；装不上 tensorrt 就以 ORT CUDA EP 兜底并记录尝试过程。
   → ✅ 完成且超出原计划：未走 Kaggle T4（无 T4 实测记录），改在本机 RTX 3050 + TensorRT 11.4 构建部署引擎，并与蒸馏学生组合为最终 GPU 交付（合并稿表2/表5）；引擎绑定本机 GPU/CUDA，跨设备需重建。
5. **infer.py 端到端接口**：读图 → letterbox → 后端推理（构造时选 pt/onnx/ov）→ NMS → 坐标还原，交付 `Detector` 类给实验 4。
   → ✅ 完成：`exp3/p2_delivery/gpu/scripts/infer.py` 统一 .pt/.onnx/.xml/.engine 入口与 `--pipeline` 端到端路径，API `from optimized_trt import Detector`；`auto_infer.py` GPU 优先、CPU 回退（同一 A2 权重的 OpenVINO 版）。
6. **报告与图**：填初稿 3.2 节占位；延迟柱状图 + 精度-速度帕累托图（可扩展 `scripts/make_figures.py`）；主表速度列补全后重出表 1。
   → ✅ 完成：初稿 3.2 占位由合并稿整体替换（`docs/实验3报告_合并稿.docx`）；P2 两份分报告在 `exp3/p2_delivery/reports/`；延迟/吞吐柱状图（合并稿图9/图10）与精度-速度权衡图（图13）齐备；主表改为双口径精度呈现（表3），速度对比独立成表5/表6/表7。

## 四、口径约束

- **ultralytics==8.4.176 锁死**（P1 全部数字在此版本测出，换版本不可比）；
- 精度一律 `yolo val model=<文件> data=data/splits/yolo/data.yaml split=test imgsz=640`（test 380 张，与实验 2 终评同集合）——**精度数字已定稿，P2 只需测速度，不必重测 mAP**（OpenVINO/TRT 新后端需测一次精度一致性）；
- 内存：CPU 用 psutil RSS 每 10 次采样取峰值；GPU 口径用 `torch.cuda.max_memory_allocated()`；
- 测速前关后台大进程，跑两遍取稳定值。

## 五、P1 关键结论备忘

1. 量化主线：体积 13.2→3.6MB（**-72.9%**），精度无损（0.419→**0.420**），远优于任务书 ≤2% 达标线；**实验 4 部署推荐 `a2_int8_val346.onnx`**。
2. 校准实验矩阵（E1/E2/E4）差异 <0.2pp → 校准集与粒度不敏感，选内置 E1 最省事。
3. 蒸馏：dis=9 最优 **0.422**（超未蒸馏基线 +0.3pp、距教师 0.424 仅 -0.2pp，任务书双达标）；dis_loss 4.07→0.92 收敛健康。
4. 蒸馏+INT8 叠加**非无损**：0.418→0.412（-0.6pp），蒸馏学生对舍入更敏感（报告难点素材）。
5. 量化误差结构性分布：中目标无损、**大目标 -3.0pp**（0.212→0.182）、小目标 test 集仅 3 框无统计意义；逐图 ΔAP 379/380 张在 ±0.1 内。
6. 噪声鲁棒性 σ=0.02：FP32 0.419→0.417、INT8 0.420→0.416，量化未放大噪声敏感性。
7. 教师 M1（v8m）位于仓库 `models/exp2/A2_yolov8m/`（目录名带 A2 是因沿用 A2 数据配置，文档里叫 M1，同一个东西）。

## 六、P2 交付已整合（2026-10-30）

P2 最终交付包原为根目录 `优化/`（zip 备份：根目录 `实验3_优化完整代码模型数据与报告.zip`），已整体移入 **`exp3/p2_delivery/`**，内部结构原样保留（脚本相对路径、PS1 启动器可直接用）。散件归档：

| 交付物 | 位置 |
|---|---|
| CPU 线（ORT/OpenVINO/INT8 矩阵）代码与结果 | `exp3/p2_delivery/{scripts,models,results}/` |
| GPU 线（TensorRT FP16 + 蒸馏温度扫参 T5/8/10） | `exp3/p2_delivery/gpu/` |
| P2 自建数据划分（原始帧 2158/173/190，无增强副本） | `exp3/p2_delivery/data/`（data.yaml 原为 P2 机器绝对路径，已改本机路径） |
| 两份正式报告 PDF（模型优化与对比验证 / CPU推理优化与验证） | `report/`（副本；原件在 `exp3/p2_delivery/reports/`，含可编辑 md） |
| 实验3任务书.pdf | `docs/`（原项目缺此文件） |
| Kaggle T4 复现入口 | `exp3/p2_delivery/kaggle/实验3_GPU复现.ipynb` |

**验收结论**（`exp3/p2_delivery/优化说明与验收.md`、`results/任务书与MD验收.json`）：主方向 3.1.4 两轮实测全部达标——单张延迟 −53.4%（复测 −55.2%）、批32延迟 −64.2%（复测 −58.0%）、吞吐 +179.4%（复测 +138.1%）、AP 最大变化 0.08pp、千次推理内存波动 ≤5%。最终选型 `a2_trt_fp16_pipeline`（10.757ms）。

**P2 数字独立复核**（`exp3/p2_check/`）：P2 的 test 集是 test 380 中 190 张原始帧（与训练集零重叠），本仓库同版本 ultralytics 复核 A2 得 mAP50 **0.987** / mAP50-95 **0.734**，与 P2 的 0.9795/0.7239 一致。

**数据质量发现（重要）**：test 380 全集 mAP50 0.419 与原始帧子集 0.987 的差距，源于另 190 张 `_aug0` 增强副本——`scripts/03_augment/augment_images.py` 在 torchvision 0.29 下 `transform(numpy图, tv_tensors框)` **框被变换、图像原样返回**（已复现：像素差 0.00），致全部 `_aug0` = 原图复制 + 标注随机平移（中位 IoU 0.000），该子集上 mAP50 仅 0.095。P1 各版本对比均用同一 test 380，相对结论不受影响；绝对精度以原始帧口径为准。

**干净口径重评（2026-10-30，A 方案）**：`exp3/scripts/eval_clean190.py` 在 190 张原始帧上重评全部版本（`exp3/results/table1_clean190.json`、`eval_detail_clean190.json`）。要点：A2 0.987/0.734、教师 0.990/0.767；INT8 真实代价显形于 mAP50-95（0.734→0.717，−1.7pp），mAP50 与各尺寸档 AP50 无损（大目标 0.961→0.961，全集口径"大目标 −3.0pp"确认为标注噪声伪影）；蒸馏 dis=9 在 mAP50-95 仍为超基线最优学生（0.736 vs 0.734）；噪声鲁棒性复测一致。报告表1 已改为全集/干净双口径呈现。

**实验2 结论勘误（同源污染伪影）**：A1 消融组（原始帧 2158、无增强）干净口径 **0.991/0.755**，反超 A2（0.987/0.734）且直逼教师——实验2 报告"A2 比 A1 +4.7pp（0.418 vs 0.371）、增强有效"系伪影：train/test 的 aug0 错标注出自同一变换（先增强后划分），A2 训练时学会了预测抖动框、在 test 的 aug0 半边得分 0.095，A1 仅 0.053，合成全集即成虚假的增强收益；干净口径下增强实为 −2pp（`exp3/results/a1_clean190.json`）。实验2 中不受影响的结论：容量对比（M1>A2，同数据内部公平）、训练流程、权重质量。

**管线修复（2026-10-30）**：`scripts/03_augment/augment_images.py` 已修复——v2 变换改为直接传入 PIL 图像（numpy 数组在该版本下不生效），并用合成图验证框与图像同步变换（变换后方块像素位置与输出框 IoU=0.980）；真实图端到端验证图像被实际变换（像素差 51/255）。历史数据未重新生成（下游无需求），如需可重跑该脚本产出正确增强副本。正式干净口径划分：`data/splits/yolo/data_clean.yaml`（train 2158 / val 173 / test 190，实验4/5 报精度一律用它）。

## 七、合并报告定稿与合规修订（2026-10-30）

**正式报告改为组内合并稿**：`docs/实验3报告_合并稿.docx`（P1 精度线 + P2 速度线合著，封面组号 17，七章结构，17 图 7 表）；修订前备份 `docs/实验3报告_合并稿_备份_改表号前.docx`。P2 交付包内两份报告 PDF（`exp3/p2_delivery/reports/`）及 `report/` 副本自此作为速度线分报告留档。

**任务书第六节"实验报告要求"四条核查结论**：

| 要求 | 状态 | 载体 |
|---|---|---|
| 1 成员构成与每人分工 | 部分：封面 6 人中 4 人分工留空，**按组内决定保持原样**（与实验1报告口径一致） | 封面分工表 |
| 2 优化对比表 + 精度损失分析（含热力图） | 达标 | 表3 双口径总表（参数量/FLOPs/体积）；图2/图3 分层与逐图误差；图15 AP 差值热力图 |
| 3 三方法速度对比 + 异构精度一致性 | 达标（本次补强） | 表5 GPU / 表6 CPU / 新增表7 统一汇总 |
| 4 关联分析两条 | 达标 | 五.8 两段（实验1 数据特点→量化误差；实验2 模型特性→剪枝敏感性） |

**本次修订内容**（只动编号/文字/新增段落，未改任何实测数据）：

1. 表编号按出现顺序重排：3.2 蒸馏训练配置→**表1**、TensorRT 引擎→**表2**、五.1 优化总表→**表3**（原表1），表4–表6 不变；全文 6 处交叉引用同步更新（含核查时发现的漏网引用"与表1 干净口径同集"→表3）。
2. 3.2 节残句"测试优：。"→"**测试与验证：**"。
3. 五.4 末新增"**任务书 3.1.3 指标复核**"段：精度项双达标（dis=9 全集 mAP50 0.422，+0.3pp 超基线 / -0.2pp 距教师，干净口径 mAP50-95 0.736 vs 0.734）；速度、体积两项判**结构性不适用**——同一 TRT FP16 流水线下未蒸馏学生单图 P50 10.757ms vs 蒸馏学生 9.69ms（约 -9.9%，未达 ≥20% 门槛），体积 6.3 vs 6.5MB（未达 ≥10% 门槛）；实际收益由任务 3.1.4（PyTorch 23.08ms → TRT FP16 9.69ms，-58.0%）与任务 3.1.1 量化（13.2→3.6MB，-72.9%）承担。
4. 五.7 末新增**表7**"推理加速方法统一对比（ONNX Runtime / TensorRT / OpenVINO，实测汇总）"：GPU 基线 23.08ms / 63.78 图/秒 vs TensorRT FP16（蒸馏学生）9.69ms（-58.0%）/ 232.37 图/秒（+264.4%）、mAP50 -0.29pp、mAP50-95 +0.47pp；CPU 基线 72.22ms / 8.98 图/秒，ORT FP32 81.42ms（+12.7%）/ 13.97 图/秒（+55.6%）/ mAP50-95 逐位一致，OpenVINO FP32 调优 56.07ms（-22.4%）/ 17.92 图/秒（+99.5%）/ 等效无损——全部数字引自表4/表5/表6，与 P2 交付实测记录一致。
5. 格式核验：新段落正文小四宋体 + Times New Roman、行距 20 磅、首行缩进两字符，表7 题注五号居中（符合 `report/模板_converted.docx` 规格）；docx postcheck 0 错误。

**引用口径提示**：

- 报告数字一律以合并稿为准；本 README 第二节"主对比表"的速度列仍是 P1→P2 交接时的待测占位，最终实测值见第六节验收数字与合并稿表5/表6/表7（占位表未回填，仅作交接历史）。
- 第五节备忘的 dis_loss 4.07→0.92 系 **dis=6 主跑**（`exp3/results/a2_distilled.json` note）；合并稿图6 的 6.04→1.34 系 **dis=9 最优组**——两组数字各有所指，引用时按组别标注。
