# 数据清理日志（2026-10-13）

> 原则：只删「字节重复 / 被成品取代 / 可重新下载重建」的文件；所有指标、日志、
> 溯源文档、清洗隔离样本一律保留。切换到"AI 赛事解说员"新方案后的第一次清理。

## 已删除项（含恢复方式）

| # | 项目 | 大小 | 为什么可删 | 需要时如何重建 |
|---|---|---|---|---|
| 1 | `data/raw/multisports/trainval.tar` | 15G | 与 `extract/`（526 段 mp4）字节级同一份内容，且 526/526 已通过清洗校验（clean_metrics: 526→526 丢弃 0） | `scripts/01_acquire/download_multisports_hf.py`（门控仓库，需 HF token） |
| 2 | `data/raw/sportsmot_hf/`（train/val tar） | 13G | 旧图像线的上游原始包（含足球排球）；篮球成品 `data/splits/yolo/` 已独立成库（829M，实验 2 冒烟验证通过） | `scripts/01_acquire/download_sportsmot_hf.py`（hf-mirror 免费重下） |
| 3 | `data/raw/sportsmot/`（篮球序列解压件） | 5.9G | 同上，转换中间产物，成品已自足 | 同上，再跑 `extract_basketball.py` + `mot_to_yolo.py` |
| 4 | `data/processed/vision/images + labels` | 1.9G | 划分前的暂存区（1280×720 原始帧）；最终 640×640 标准化版本全部在 `data/splits/yolo/`（5042 张名称集合核对一致） | 重跑 `standardize_and_split.py`（源见 #2） |
| 5 | `models/`、`runs/` 冒烟残留 | 40M | 本轮 CPU 冒烟测试产物（1 epoch × 5% 数据），非正式权重 | 随时重跑 `train_yolo.py --fraction 0.05` |
| 6 | `data/processed/vision/quarantine/` **部分** | 634M→220M | ~~近重复剔除隔离区~~ **中途叫停**：原 2460 张已删约 1544 张，**剩余 916 张保留不再动** | 剔除记录在 `vision/clean_metrics.json`（near_duplicates: 2460），方法在 `scripts/02_clean/clean_images.py` |
| 7 | 结构化 CSV 三层（2026-10-13 用户决定） | ~689M | `data/raw/stats/`（Kaggle 原始）+ `data/processed/structured/` 全部 CSV + `data/splits/structured/`；新方案主线已不用结构化统计（用户此前已定），实验 1 报告已提交不受影响 | `scripts/01_acquire/acquire_structured_stats.py`（需 Kaggle 账号）→ `clean_structured.py`；五表清洗指标 json 已留档 |
| 8 | 项目根目录（2026-10-13） | ~120K | 删 `__pycache__` ×6 与 `sohu_nba_page.html`（爬虫调试残留）；根目录 8 个旧运行日志**移入 `logs/`**（未删） | 日志在 `logs/`；pycache 自动再生 |

## 明确保留项（即使"用不到"也留）

- `data/processed/vision/` 的全部指标/溯源小文件：`clean_metrics.json`、`manifest.json`、`game_provenance.csv`、`augment_log.json` —— 实验 1 报告（已提交）的清洗证据链；
- `data/processed/structured/` 的五表清洗指标 json —— 结构化线的清洗证据链（CSV 本体已于 #7 删除）；
- `data/processed/texts/` 122 篇资讯 —— 推导文档定为"过渡案"RAG 语料；
- `data/raw/texts/livetext/` 全部原始 jsonl —— 解说语料的原始层，一切清洗的溯源起点。

## 清理后基线

- 磁盘可用：59G → 93G（释放 34G）
- data/ 目录只保留：成品数据集（splits/yolo、vision_ms、解说三分卷）、MultiSports 视频（526 段）、GT 标注、各层指标文件
- `exp2_colab_pkg.tar`（818M）：上传 Colab 完成训练后删除

## 恢复记录（2026-10-13 晚）

用户复核后认为 #2/#3（SportsMOT 原始包）不该删，当晚从源头完整重建：

| 项目 | 结果 |
|---|---|
| `data/raw/sportsmot_hf/train.tar`（6.70 GB） | 重下完成，大小 6,703,191,552 字节与官方记录一致 |
| `data/raw/sportsmot_hf/val.tar`（6.59 GB） | 重下完成，大小 6,592,876,544 字节与官方记录一致；`splits_txt/`（basketball/train/val.txt）一并取回 |
| `data/raw/sportsmot/basketball/`（5.9 GB） | `extract_basketball.py` 重跑恢复：30 个含 gt 序列（= 篮球∩train+val 划分，与 `processed/vision/manifest.json` 的 30 个序列逐一吻合），24,941 张帧图像、227,673 条 gt 行，各序列 `seqinfo.ini` 声明帧数与实际全部一致 |
| 过程记录 | hf-mirror 间歇性重置连接（curl 35），靠脚本断点续传 + 自动重试（3 分钟冷却 × 14 轮）完成；日志 `logs/sportsmot_redownload.log`、`logs/sportsmot_extract.log` |

说明：`splits_txt/basketball.txt` 共 80 个序列，其中 50 个属 test 划分（在未下载的 test.tar 中，官方无 gt 标注）——提取脚本报"缺少 gt 的序列 50 个"即此，属预期，非数据缺失。

## 后续清理约定

任何删除动作前：① 对照本日志"可删判定"；② 涉及清洗记录/报告证据的，一律不删；③ 删除后在本日志追加一行。
