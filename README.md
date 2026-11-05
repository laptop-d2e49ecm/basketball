# 篮球 AI 赛事解说员 —— 课程项目总仓库

## 当前 Web 应用（第三版）

**最新版入口：[exp4/complete_web_system](exp4/complete_web_system/README.md)**。前端、配套后端、模型和样例都在此目录；下载后按说明安装依赖，双击 `start_project_v3.bat`。旁边的 [complete_web_system.zip](exp4/complete_web_system.zip) 与该目录同步。

默认 `master` 已更新为第三版，固定标签为 `frontend-v3.0.0`。第一版 `frontend-v1.0.0`、第二版 `frontend-v2.0.0` 保留原提交。`exp4/frontend/`、`exp4/backend/` 是早期模块源码，当前完整系统请使用上述目录。

**最终成品**：上传一段篮球比赛视频 → 系统看懂画面（谁在哪儿、发生了什么动作）→ 用中文实时生成逐事件解说。

课程 5 个实验串成这条流水线：**数据（实验1）→ 球员检测（实验2）→ 模型优化（实验3）→ Web 系统（实验4）→ 大模型 Agent 解说（实验5）**。

> 本 README 是实验 1/2/3 的**全部真实执行记录**（数字均可在仓库指标 json 与训练产物中复核）。
> 数据溯源见 `docs/PROVENANCE.md`，实验 2 选型与结果口径见 `docs/EXP2_MODEL_SELECTION.md`，
> 云端训练步骤见 `docs/COLAB_STEPS.md`，2026-10-13 数据清理记录见 `docs/CLEANUP_LOG.md`。
> 实验 3 全档案索引 `models/exp3/README.md`，正式报告 `report/实验3报告.docx/pdf`（P1+P2 合并稿）。
> **注意**：实验 3 复核发现实验 1 增强副本存在标注缺陷并勘误了实验 2 的增强收益结论，见实验 3 节。

---

## 实验 1：数据采集与预处理（2026-10-08 完成）

### 1.1 数据成果总览

| 数据线 | 内容 | 规模 | 划分（8:1:1，seed=42） | 位置 |
|---|---|---|---|---|
| 视频+动作标注 | MultiSports 篮球子集（mp4+逐帧框+18 类动作） | 526 段 / 6247 动作实例（720p@25fps） | 随官方 train/val（379/147） | `data/raw/multisports/` |
| 检测图像（主） | SportsMOT 篮球子集转 YOLO 格式（640×640） | 5042 帧（含 `_aug0` 增强副本） | 按序列 24/3/3 → 帧 4316/346/380 | `data/splits/yolo/` |
| 检测图像（补充） | MultiSports 有标注帧 2fps 截取 | 7746 帧 / 9094 框 | 随视频官方 split | `data/processed/vision_ms/` |
| 解说文本 | 直播吧文字直播逐条记录（时间戳/解说员/当时比分） | 41 场 40,376 条 | 按场次 33/4/4（32,377/4,889/3,110 条） | `data/processed/texts/livetext/` |
| 事件表 | 动作实例结构化（视频/动作/起止帧与秒/框坐标） | 6247 行 CSV | 随视频官方 split | `data/processed/multisports/events.csv` |
| 资讯 | 篮球资讯 120 篇 | — | 按行同比例 | `data/processed/texts/` |

### 1.2 多源获取（合规方式均为真实执行）

- **视频线（门控仓库）**：MultiSports 为 HuggingFace 门控仓库，镜像站不转发 Authorization 头导致 401，改为携带 Bearer token 直连官方域名，仅下载含标注的 trainval 拆分（15.55GB）；token 仅经环境变量传递、不落盘。
- **图像线（公开数据集）**：SportsMOT（CC BY-NC 4.0 非商业）经 hf-mirror 镜像以 HTTP Range 分段断点续传下载；下载器内置 DoH 解析真实 IP 并用 `curl --resolve` 钉住，绕过本机 DNS 劫持。解包后仅提取篮球子集，MOT 标注转 YOLO 归一化坐标、每 5 帧抽样。
- **解说线（合规爬取）**：直播吧文字直播接口由页面 JS 逆向得到（分页 JSON、每页 10 条、33 字段）。先检查 robots.txt 确认未触碰 Disallow 路径，限速 0.5 秒/页、3 并发、断点续爬、User-Agent 携带课程标识；针对接口对超界页码返回末页导致的翻页死循环，以"整页记录 ID 与已爬集合完全重复即终止"+200 页硬上限双重防护。共采集 41 场完整比赛 40,923 条。
- **资讯**：篮球资讯 122 篇（robots.txt 检查、2 秒限速、GBK 编码自动探测）。

### 1.3 清洗与增强（前后数字均落盘 `clean_metrics.json`）

| 数据线 | 清洗前 | 清洗后 | 主要操作 |
|---|---|---|---|
| 视频 | 526 段 | 526 段（0 剔除） | 首/中/尾帧解码、帧数与标注对齐（±2 帧）、分辨率帧率核对 |
| 图像 | 4981 帧 | 2521 帧（剔近重复 2460，49.4%） | 损坏检测、EXIF 抹除、感知哈希（汉明距离≤6）近重复隔离至 quarantine、标注越界校验 |
| 解说 | 40,923 条 | 40,376 条 | 去空 386/超短 159/重复 1/无字 1；33 字段统一为 5 字段（场次/时间/文本/解说员/比分） |
| 资讯 | 122 篇 | 120 篇 | Data-Juicer 六算子策展（MinHash 去重 2 篇） |

**图像增强**：torchvision transforms v2 组合水平翻转+仿射平移缩放+色彩抖动，检测框与图像同步几何变换（像素/归一化坐标显式互转），2521→5042 帧，仅 51 个出画/过小框被丢弃；增强副本以 `_aug0` 后缀跟随原帧落位同侧集合，保证增强不引入划分泄漏。**文本不做同义替换类增强**（避免解说语义失真），实验 5 再构造"事件—解说"指令对。
**（实验 3 勘误 2026-10-30）**：复核发现该管线仍有隐蔽缺陷——torchvision 0.29 下 numpy 图像传入 v2 变换时**框被变换而图像原样返回**，全部 `_aug0` 副本实为"原图+错位标注"；脚本已修复但历史副本未重生成，详见实验 3 节。

### 1.4 标准化划分与防泄漏

图像统一 640×640、按**比赛序列**8:1:1 划分（同一序列的全部帧及增强副本落位同一子集）→ train/val/test = 4316/346/380 帧（24/3/3 序列，val 含 3104 个标注框）；解说语料按**场次**划分（33/4/4 场）。二者从源头保证同一场比赛内容绝不跨 train/val/test，避免验证指标虚高。PyTorch Dataset 封装（`src/basketball_dataset.py`）加载验证通过，检测数据集另经 ultralytics 实际加载冒烟（346 张验证图、3104 框全部正确配对、训练循环跑通）。

### 1.5 自动化策展与手工清洗效率对比（同一 122 篇语料）

手工脚本 `clean_texts.py` 0.29 秒（122→122）vs Data-Juicer 1.6.0 六算子流水线 134 秒（122→120，含 fasttext 语言模型加载约 20s）。算子：`clean_html_mapper`、`whitespace_normalization_mapper`、`language_id_score_filter`（中文≥0.5）、`text_length_filter`（50–10000 字）、`clean_email_mapper`、`document_minhash_deduplicator`（字符级 MinHash、128 置换、Jaccard 0.7）；配置 `configs/data_juicer_text.yaml`，default 执行器。小语料下手工快约两个数量级，Data-Juicer 价值在算子可组合、流程可复现、可扩展至大规模语料。

### 1.6 四维数据质量评分（`quality_report.py`）

完整性 100（损坏 0、标注异常 0）、一致性 100（保留集内重复 0）、代表性 81.2（30 个序列帧数基尼系数 0.188）、时效性 90，**综合 92.8/100**。

### 1.7 关键问题与解决（全部真实踩坑）

1. **门控仓库 401**：镜像不转发 Authorization 头 → Bearer token 直连官方域名，token 不落盘。
2. **本机网络异常**：Clash TUN 接管 DNS（fake-ip）且系统代理极慢 → DoH 解析真实 IP + `curl --resolve` 钉住；urllib 以空代理配置构建 opener，恢复 0.5 秒/页。
3. **翻页死循环**：接口对超界页码返回末页而非空页 → 整页 ID 与已爬集合完全重复即终止 + 200 页硬上限。
4. **增强与标注一致性**：坐标系错误会把框压成一点 → 像素/归一化坐标显式互转，出画/过小框按阈值丢弃并计数。
5. **数据泄漏防护**：按序列/场次而非按行随机划分。
6. **py-data-juicer 1.6.0 兼容**：入口 `dj-ce` 移除（改 `dj-process`）、process 段须为单键字典列表、selectolax 1.0 移除 modest 后端导致静默清空（降级 0.3.28）、默认 ray 执行器装不上（改 default）。
7. **torch DLL WinError 1114**：Anaconda 自带 2020 版 msvcp140.dll 先于系统目录加载 → 经 Windows 事件日志崩溃签名定位，以系统新版运行库覆盖旧版彻底修复。

---

## 实验 2：模型设计与训练（2026-10-19 完成，产物 10-22 归档）

### 2.1 任务、环境与选型

- **任务**：单类目标检测（类别 `player`，nc=1）——由实验 1 的 YOLO 格式球员框标注决定，输出逐球员边界框坐标。
- **环境**：本地 PC（AMD Ryzen 7 6800H、14GB RAM、无独立显卡）负责代码编写与数据校验；正式训练在 Kaggle（NVIDIA Tesla T4×2 免费 GPU）。云端软件：Python 3.13、PyTorch 2.11.0、Ultralytics 8.4。
- **选型**：真实比赛球员密集、遮挡严重 → 单阶段检测器 YOLOv8；搭建轻量 YOLOv8n（约 3.2M 参数，满足前端实时需求）与中等规模 YOLOv8m（约 25.9M）横向对比容量收益。

### 2.2 云端只读数据适配（关键技术点）

Kaggle 数据集挂载在 `/kaggle/input`（只读），YOLO 无法生成 cache、本地绝对路径的 train 清单在 Linux 下失效。解决：脚本动态扫描 `images/train` 真实图片、剔除 `_aug0` 增强副本，在可写的 `/kaggle/working` 重新生成绝对路径 txt 清单与 yaml 配置。仓库版已整合进训练入口：`train_yolo.py --data-root /kaggle/input/<数据集名> --work-dir /kaggle/working` 自动完成适配。

### 2.3 消融实验设计与超参

脚本共支持 8 组对比（`scripts/03_train/train_yolo.py` 的 RUNS）：A1/A2 = YOLOv8n 增强消融；B1/B2 = YOLOv8s；M1 = YOLOv8m 容量探索（batch=8）；C1/C2 = YOLO11 代际；D1 = YOLOv5n。**实际执行核心 3 组（A1/A2/M1）**，B/C/D 为可选扩展。

固定超参（三组一致，见各组 `args.yaml`）：`epochs=50, patience=15, cos_lr=True, amp=True, seed=42, imgsz=640`，batch=16（M1 为 8），加载 COCO 预训练权重迁移学习。数据口径：A1 用 train 集原始帧 **2158** 张，A2 用增强后 train 集 **4316** 张（全数据集口径为 2521/5042）。

### 2.4 训练结果（真实 `results.csv`，best.pt 验证集口径）

best.pt 由综合适应度（0.1×mAP50+0.9×mAP50-95）选轮；耗时为 results.csv 时间列累计值：

| 组 | 模型 | 参数量 | best.pt 轮次 | mAP50 | mAP50-95 | 训练耗时 | 全程最高 mAP50 |
|---|---|---|---|---|---|---|---|
| A1 | YOLOv8n | 3.2M | 第 49 轮 | **0.371** | 0.245 | 0.27 h（958s） | 0.372 @16 |
| A2 | YOLOv8n | 3.2M | 第 43 轮 | **0.418** | 0.262 | 0.50 h（1811s） | 0.422 @34 |
| M1 | YOLOv8m | 25.9M | 第 50 轮 | **0.424** | 0.271 | 1.69 h（6098s） | 0.427 @40 |

- **增强因果验证（任务书必填）**：仅数据一个变量不同，A2−A1 = **+4.7 个百分点** mAP50（0.371→0.418），验证实验 1 几何+色彩增强对泛化能力的因果收益。**（实验 3 勘误：此收益系评测集 `_aug0` 错位标注的同源污染伪影——A2 训练时学会了预测抖动框；干净口径 A1 反超 A2，增强真实收益为负，见实验 3 节）**
- **容量权衡**：v8m 参数量为 v8n 的 8 倍、耗时 3.4 倍，mAP50 仅 +0.006（0.418→0.424）——4000 张级数据下瓶颈在分辨率与数据规模而非模型容量；考虑前端实时需求，**YOLOv8n 为部署选型**。
- **A2 混淆矩阵**（验证集 3104 框）：正确检出 2815、漏检 289（召回 90.7%）；左下为低置信阈值下全部误检框（约 9460，模型实际取最优阈值 precision≈0.60）；右下恒空系 YOLO 混淆矩阵不统计背景-背景的设计。
- **防泄漏严谨性**：严格继承实验 1"按序列划分"，比赛相邻帧高度相似时避免同源内容跨集合，mAP 指标客观可信。

### 2.5 训练优化策略实际表现

三组均完整跑满 50 轮、验证 Loss 全程未上翘，早停（patience=15）作为防过拟合保险未触发；cos_lr=True 使后期学习率衰减平滑、30-50 轮 mAP 曲线平稳上升；AMP 混合精度下 A2（v8n，4316 张×50 轮）全程仅 0.5 小时。

### 2.6 训练产物与复现

- **产物**：`models/exp2/{A1_yolov8n, A2_yolov8n, A2_yolov8m}`——各组 `results.csv`、`args.yaml`、`weights/best.pt`、训练曲线 `results.png`、混淆矩阵与 val_batch 预测图（2026-10-22 归档）。逐组选轮口径与 8 组设计详见 `docs/EXP2_MODEL_SELECTION.md`。
- **复现**：

```bash
# 本地 CPU 冒烟（验管道，1 epoch × 5% 数据）
python scripts/03_train/train_yolo.py --run A2 --epochs 1 --fraction 0.05 --imgsz 480 --device cpu

# Kaggle 正式训练（三组约 2.5 小时；--data-root 指向只读挂载自动生成清单与 yaml）
pip install ultralytics
python scripts/03_train/train_yolo.py --run A1,A2,M1 --epochs 50 --patience 15 --device 0 \
  --data-root /kaggle/input/<数据集名> --work-dir /kaggle/working
# 其余可选组：--run all（B/C/D 未执行）；关闭余弦调度对照：--no-cos-lr（详见 docs/COLAB_STEPS.md）
```

---

## 实验 3：模型压缩与推理优化（2026-10-30 完成）

正式报告 `report/实验3报告.docx/pdf`（P1+P2 合并稿，17 图 7 表），全档案索引与产物清单 `models/exp3/README.md`。优化对象：实验 2 部署选型 **A2 YOLOv8n**（mAP50 0.419，ultralytics 8.4.176 锁版复测）与教师 **M1 YOLOv8m**（0.424）。

### 3.1 分工与主线

两人双线并行：**P1 精度线**（INT8 静态量化、前景加权特征蒸馏、误差与鲁棒性分析；本地 CPU + Kaggle T4）与 **P2 速度线**（复合损失蒸馏、TensorRT FP16 引擎与端到端流水线、CPU 三后端对照；本机 RTX 3050）。产物：`models/exp3/models/` 10 个模型、`results/` 13 个 JSON + 图表、`p2_delivery/`（CPU/GPU 全套脚本与两轮复测）、`p2_check/`（独立复核）。

### 3.2 主结果（双口径：全集 test 380 与干净 test 190 原始帧）

| 版本 | 精度 | 体积(MB) | mAP50(380) | mAP50(190) | mAP50-95(190) |
|---|---|---|---|---|---|
| A1 无增强消融（复核） | FP32 | 6.2 | 0.371 | **0.991** | **0.755** |
| A2 PyTorch（基线） | FP32 | 6.5 | 0.419 | 0.987 | 0.734 |
| M1 YOLOv8m（教师） | FP32 | 50 | 0.424 | 0.990 | 0.767 |
| **INT8 E1（val346，部署推荐）** | INT8 | **3.6** | **0.420** | 0.988 | 0.717 |
| 蒸馏 dis=9（最优学生） | FP32 | 6.3 | **0.422** | 0.983 | 0.736 |
| 蒸馏+INT8 叠加 | INT8 | 3.5 | 0.412 | 0.985 | 0.714 |
| 蒸馏(T6)+TRT FP16（P2 交付） | FP16 | 9.3 | — | 0.977 | 0.729 |

- **量化（任务 3.1.1）**：ONNX 13.2→3.6MB（**-72.9%**），精度无损（0.419→0.420）；校准实验 E1/E2/per-channel 差异 <0.2pp，校准集与粒度不敏感。干净口径下真实代价显形于定位精度：mAP50-95 -1.7pp（0.734→0.717），mAP50 与各尺寸档无损。关键工程点：检测头解码（DFl/Softmax/坐标）保持 FP32，避免概率分数舍入归零。
- **蒸馏（任务 3.1.3）**：单类检测下 KL 信息量退化——P1 用前景加权特征蒸馏（dis∈{3,6,9} 消融），**dis=9 最优 0.422**（超基线 +0.3pp、距教师 -0.2pp，任务书双达标）；P2 按任务书 0.3/0.7 口径复合损失（0.3·Ldet+0.5·Lfeat+0.2·LKD，Bernoulli KL，温度 T=5/8/10 扫参选 T=6）。蒸馏不改变学生结构（3.13M 参数/8.6 GFLOPs 不变）；蒸馏后再量化存在 -0.6pp 交互损失（干净口径下基本消失）。
- **推理加速（任务 3.1.4 + 阶段 2）**：GPU（RTX 3050）PyTorch 23.08ms → TensorRT FP16 **9.69ms（-58.0%）**、批 32 吞吐 63.78→232.37 图/秒（**+264.4%**）；CPU（Ryzen 7 5800H）OpenVINO FP32 调优 72.22→56.07ms（-22.4%）、吞吐 +99.5%，ORT 吞吐 +55.6%。噪声鲁棒性 σ=0.02 下 FP32/INT8 均无损；千次推理内存波动 ≤5%。
- **部署选型矩阵（实验 4 已采用）**：CPU 体积优先 → `a2_int8_val346.onnx`（3.6MB，图像检测 API）；CPU 精度保守 → OpenVINO FP32；GPU → 蒸馏学生 TRT FP16 引擎；精度替补 → `a2_distill_dis9.pt`。统一 `Detector` 端到端接口（.pt/.onnx/.xml/.engine）随 P2 交付实验 4。

### 3.3 数据质量重大发现：`_aug0` 标注缺陷与实验 2 勘误

评测复核发现实验 1 增强管线的隐蔽缺陷：torchvision 0.29 下 numpy 图像传入 v2 变换，**标注框被变换而图像原样返回**（复现：像素差 0.00）——全部 `_aug0` 副本实为"原图复制 + 随机错位标注"（框与内容中位 IoU 0.000）。test 380 中 190 张 `_aug0` 上模型 mAP50 仅 0.095，把全集绝对精度压至 0.419；**模型真实水平为干净 190 原始帧上的 0.987（A2）/0.991（A1）/0.990（教师）**。

由此勘误实验 2 结论：干净口径 **A1 反超 A2**（0.991 vs 0.987）——"+4.7pp 增强收益"系训练与评测标注同源污染的伪影，增强真实收益为负（恰为任务书提示需避免的无效增强情形）；A2 作为部署选型依然合格（0.987），选型无需翻案。实验 2 不受影响的结论：容量对比（M1>A2，同数据内部公平）、训练流程、权重质量。

管线已修复（2026-10-30）：v2 变换改传 PIL 图像，合成图验证框图同步（IoU 0.980）；历史副本未重生成（下游无需求）。正式干净划分 `data/splits/yolo/data_clean.yaml`（train 2158 / val 173 / test 190，无增强副本），**实验 4/5 报精度一律用它**。

---

## 脚本流水线（`scripts/`，原始包可按 CLEANUP_LOG 重建）

```
阶段 1 获取   01_acquire/  download_multisports_hf（门控仓库 Bearer 直连）· download_sportsmot_hf（镜像分段断点续传）
             crawl_zhibo8_livetext（接口逆向+合规限速）· crawl_basketball_news · multisports_to_yolo/events 等转换
阶段 2 清洗   02_clean/    clean_multisports（526/526 通过）· clean_images（感知哈希去重）· clean_livetext ·
             clean_texts + run_dj（Data-Juicer 六算子）
阶段 3 增强   03_augment/  augment_images（框同步变换；2026-10-30 修复 v2 变换 numpy 入参
             不生效缺陷，历史 _aug0 副本未重生成，见实验 3 节）；训练入口 train_yolo.py
阶段 4 标准化 04_standardize/ standardize_and_split（640×640、按序列 8:1:1、data.yaml）
阶段 5 评估   05_evaluate/ quality_report（四维评分）· 图表生成
```

## 环境

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt        # 2026-10-13 起含 ultralytics
```

本地环境：Windows 11 · Python 3.11.5（venv）· torch 2.14.0+cpu · torchvision 0.29.0 · py-data-juicer 1.6.0 · pandas 3.0.6 · scikit-learn 1.9.1 · imagehash · beautifulsoup4 · requests。

## 目录结构

```
basketball/
├── data/
│   ├── raw/multisports/      # 526 段 mp4 + multisports_GT.pkl（事件表源头）
│   ├── raw/texts/livetext/   # 解说原始 jsonl（每场一个）+ crawl_meta.json
│   ├── processed/            # multisports（events.csv）/ vision_ms（补充帧）/ vision / texts
│   └── splits/               # yolo/（实验2主数据集 4316/346/380）+ split_summary.json
├── scripts/                  # 01 获取 / 02 清洗 / 03 增强+训练 / 04 标准化 / 05 评估
├── configs/                  # Data-Juicer 配置（解说语料复跑待用）
├── src/                      # PyTorch Dataset 封装（任务 1.3.2）
├── docs/                     # 推导/溯源/数据卡/合规/清理日志/实验2选型/云端步骤
├── logs/                     # 各步骤运行日志（历史记录）
├── models/exp2/              # 实验 2 训练产物：A1_yolov8n / A2_yolov8n / A2_yolov8m(=M1)
│                             # （results.csv、best.pt、训练曲线与混淆矩阵，2026-10-22 归档）
├── models/exp3/              # 实验 3 优化产物：10 个模型（INT8/蒸馏系）、results 13 JSON、
│                             # p2_delivery（CPU/GPU 全套）、p2_check 复核，档案 README.md
├── exp4/                     # 实验 4 Web 系统（进行中：FastAPI 后端 + Vue3 前端）
└── report/                   # 实验报告与图表（实验3正式报告 docx/pdf 在此）
```

## 实验报告要求 ↔ 产物对照

| 报告要求 | 产物 |
|---|---|
| 实验1：获取全流程（代码+问题与解决） | `scripts/01_acquire/` + `docs/PROVENANCE.md` |
| 实验1：清洗前后质量指标 | `data/processed/*/clean_metrics.json`、`convert_metrics.json` |
| 实验1：增强效果评估 | `_aug0` 消融设计 → 实验 2 A1/A2 实测 +4.7pp（上表） |
| 实验1：自动化策展配置与效率对比 | `configs/data_juicer_text.yaml`（134s vs 手工 0.29s） |
| 实验1：数据卡 + 隐私合规 | `docs/DATA_CARD.md`、`docs/PRIVACY_CHECKLIST.md` |
| 实验2：数据-模型关联 | YOLO 格式单类框 → YOLOv8 检测（nc=1 `player`） |
| 实验2：增强因果对比实验 | A1 vs A2（0.371 → 0.418），`models/exp2/` 真实产物 |
| 实验2：训练优化与容量对比 | `models/exp2/*/results.csv` + `docs/EXP2_MODEL_SELECTION.md` |
| 实验3：优化对比表 + 精度损失分析 | `report/实验3报告.pdf` 表3 双口径总表、图2/3/15 分层与逐图误差 |
| 实验3：速度对比 + 异构硬件一致性 | 报告表5（GPU TRT）/ 表6（CPU ORT/OpenVINO）/ 表7 汇总 |
| 实验3：关联分析（数据→量化误差 / 模型→剪枝） | 报告五.8 两段 + `models/exp3/README.md` |

## 下一步（实验 4-5 衔接）

实验 3 已交付部署矩阵与统一 `Detector` 接口。实验 4 Web 系统（进行中，`exp4/`）：图像检测 API 用 `a2_int8_val346.onnx`，视频主线用 A2 best.pt + ByteTrack，框坐标契约一律归一化（实验 1 坐标 bug 的教训已写进实验 4 交接契约）。实验 5 动作识别（MultiSports 18 类）+ 大模型 Agent 解说（4.0 万条语料 RAG 与风格微调）；实验 4/5 报精度一律用 `data_clean.yaml` 干净口径。
