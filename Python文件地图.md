# Python 文件地图

> 全项目 **198 个活跃 .py 文件**（另有 45 个在 `_归档/`，见文末）。用途以每个文件的 docstring / 首行注释为依据。
> 一条主线串起来：**数据工程（实验1）→ 球员检测（实验2/3）→ Web 系统 + Agent + 动作识别（实验4/5）→ 解说稿 + 语音 + 对话（成品）**。

---

## A. exp4/complete_web_system/backend —— 上线运行的 Web 系统（实验4+5 部署形态，58 个文件）

整个系统的心脏：FastAPI 后端 + 本地 Worker，前端页面（前端第三版.html）的所有功能都由这里支撑。

### app/main.py 与核心配置
| 文件 | 用途 |
|---|---|
| `app/main.py` | FastAPI 应用组装：挂载全部路由、静态页面、WebSocket、统一异常处理 |
| `app/core/config.py` | 全部配置的唯一入口：读 .env（模型路径、动作识别开关/阈值/冷却、解说后端等） |
| `app/core/coords.py` | 坐标换算：归一化 xyxy ↔ 像素坐标（前后端与训练侧的统一口径） |
| `app/core/device.py` | 推理设备选择（auto / cpu / gpu） |
| `app/core/errors.py` | 统一异常→错误码映射（400/404/429/504…），前端拿到的错误都长一个样 |

### app/db/ —— SQLite 存储
| 文件 | 用途 |
|---|---|
| `app/db/database.py` | SQLite 连接与建表（tasks.db） |
| `app/db/task_repo.py` | 任务仓库：建任务、查任务、**原子认领**（防多 Worker 重复消费）、进度更新 |
| `app/db/agent_sessions.py` | Agent 会话历史存储（断点续聊，与任务同库） |

### app/schemas/ —— Pydantic 数据模型
| 文件 | 用途 |
|---|---|
| `app/schemas/envelope.py` | 统一响应包 `{code, result, msg}`（所有接口的返回格式） |
| `app/schemas/demos.py` | 图像检测 / 文本分类 / 图文匹配三个 demo 的请求响应模型 |
| `app/schemas/tasks.py` | 视频任务、事件、进度等模型（含画面观察、动作字段） |

### app/api/ —— HTTP 接口
| 文件 | 用途 |
|---|---|
| `app/api/tasks.py` | **视频任务全生命周期**：上传、列表、进度、删除、事件/检测查询、预览视频、整场解说稿读取/重试、**解说语音 MP3**（/narration/audio） |
| `app/api/agent.py` | AI 对话接口 POST /api/v1/agent/chat（页面对话框和提问框的后端） |
| `app/api/detect.py` | 图像球员检测 demo（PNG/JPG ≤10MB，返回归一化框） |
| `app/api/text.py` | 解说文本动作分类 demo（输入一句话→动作类别） |
| `app/api/match.py` | 图文匹配 demo（图像+文本联合） |

### app/services/ —— 图像/文本/预览服务
| 文件 | 用途 |
|---|---|
| `app/services/image_detector.py` | ONNX 图像球员检测（a2v2_int8.onnx，实验3 的产物在此服役） |
| `app/services/image_inputs.py` | 图像/文本输入校验（格式、大小、非空） |
| `app/services/image_batch_store.py` | 批量图像上传的存储与查询 |
| `app/services/model_access.py` | 模型加载与单例访问（避免重复加载大模型） |
| `app/services/text_classifier.py` | joblib 文本动作分类器（实验4 产物） |
| `app/services/match_workflow.py` | 图文匹配编排（图像检测+文本分类组合出结果） |
| `app/services/video_preview.py` | 预览视频生成（带检测框）与任务数据清理 |

### app/agent/ —— 大模型 Agent（实验5）
| 文件 | 用途 |
|---|---|
| `app/agent/providers.py` | 大模型接入层：读 .env 构造 ChatOpenAI（直连不走系统代理，防 Clash 劫持） |
| `app/agent/graph.py` | Agent 核心：LangChain create_agent 初始化 + 系统提示（先查事件再回答、分页、禁止编造） |
| `app/agent/tools.py` | 把后端服务封装成 Agent 工具：query_video_events（支持 offset/limit 分页）等 |
| `app/agent/lora_classifier.py` | 可选 LoRA 后端：用实验5 微调的 Qwen3-1.7B 做"解说→动作"分类 |
| `app/agent/smoke.py` | Agent 单轮冒烟脚本（任务书 5.3.2） |

### app 其余
| 文件 | 用途 |
|---|---|
| `app/tts.py` | 整场解说语音合成（edge-tts 晓晓音色，MP3 缓存于任务目录、解说稿更新自动重合成） |
| `app/ws/task_ws.py` | WebSocket /ws/task/{id}：分析进度实时推送（前端进度条的数据源） |

### worker/ —— 分析流水线（视频进来后发生的事）
| 文件 | 用途 |
|---|---|
| `worker/main.py` | Worker 主循环：轮询 DB 认领任务 → 调 video_service 处理 |
| `worker/video_service.py` | **主管线**：读视频→YOLO 检测→ByteTrack 跟踪→动作识别→事件→逐条解说→整场解说稿→写产物 |
| `worker/action_service.py` | 3D 动作识别：按 track 滑窗裁剪（与训练同口径）喂 MC3D-18 ONNX，置信度过滤+4×4 分区冷却去重 |
| `worker/event_service.py` | 启发式事件兜底（人数变化等；动作模型不可用时保底出事件） |
| `worker/narration_service.py` | 整场解说稿：Agent 分页查完全部事件逐段写稿，疑似/可能措辞+禁词重试，失败可重试不丢结果 |
| `worker/commentary/base.py` | 解说生成器接口契约（generate / generate_batch） |
| `worker/commentary/stub.py` | 模板句解说（无需 LLM 的兜底实现） |
| `worker/commentary/llm.py` | LLM 解说：批量一次出 N 条（省配额）、行号前缀解析、403/429 熔断冷却 |
| `worker/commentary/vision.py` | 视觉看帧：抓事件时刻关键帧交视觉大模型描述（解说的第二事实源，5 秒时间桶复用） |
| `worker/celery_app.py` / `celery_tasks.py` | 可选 Celery 任务后端（默认不用，本地 worker 即可） |

### tests/ —— 34 条单元测试
| 文件 | 用途 |
|---|---|
| `tests/test_action_events.py` | 动作事件流：阈值、背景类、分区冷却、窗口最少帧数、裁剪口径 |
| `tests/test_commentary.py` | 解说：默认 stub、LLM 异常回退、批量行号、去重与上限 |
| `tests/test_coords.py` | 坐标换算往返、非法尺寸 |
| `tests/test_demo_apis.py` | 图像/文本/匹配 demo 接口的响应契约 |
| `tests/test_narration_service.py` | 整场解说：分页读全事件、失败留存重试、禁词重写 |
| `tests/test_narration_api.py` | 解说稿读取/重试接口 |
| `tests/test_narration_audio.py` | 语音合成：分段合成、缓存复用/失效重合成、接口错误映射 |

---

## B. exp5/ —— 实验5：微调线与评估（17 个文件）

| 文件 | 用途 |
|---|---|
| `train_lora.py` | Qwen3-1.7B + QLoRA 微调（4-bit 量化/LoRA/梯度累积三件套） |
| `data/build_finetune_data.py` | 微调数据构建（解说→动作的指令对） |
| `data/audit_data.py` | 微调数据质量审计：分类器一致性+逐条复核 |
| `eval/prompt.py` | 训练与评测共用提示词（唯一来源，保证对比公平） |
| `eval/baseline.py` | 基线：joblib 分类器 vs 大模型零样本各考 10 题 |
| `eval/eval_finetuned.py` | 出分：未微调基座 vs 基座+LoRA 同卷对比 |
| `eval/eval_extended.py` | 扩展评估（10 题太少，扩题审计用） |
| `eval/tool_accuracy.py` | 工具调用准确率 10 轮（报告硬指标 ≥90%） |
| `eval/agent_latency.py` | Agent 全链路量化延迟对比 |
| `eval/quant_latency.py` | 4-bit vs fp16 推理延迟与显存对比 |
| `eval/error_injection.py` | 异常注入验证错误码契约（超时 504/限流 429/空消息 400/坏会话 404） |
| `eval/rag_smoke.py` | RAG 检索工具冒烟（检索质量与路由） |
| `eval/firefox_e2e.py` | Selenium+Firefox 真实跑一次 /agent 问答（跨浏览器验证） |
| `eval/shot_video_commentary.py` | 抓"视频解说 LLM 化"验收截图 |
| `smoke_agent.py` / `test_agent_api.py` / `test_api.py` | Agent 冒烟入口 / 契约用例可执行版 / 大模型连通性自检 |

---

## C. models/ —— 实验2/3：检测模型训练、蒸馏与交付（76 个文件）

### exp2_v2（1 个）
| 文件 | 用途 |
|---|---|
| `exp2_v2/eval_test190.py` | 实验2 v2 重训模型在 test190 原始帧的终评（与 A1 同尺子） |

### exp3/scripts（6 个）—— 实验3 第一阶段（蒸馏+量化）
| 文件 | 用途 |
|---|---|
| `distill_yolo.py` | M1(YOLOv8m 教师)→A2(YOLOv8n 学生) 知识蒸馏训练 |
| `eval_clean190.py` | 干净口径重评（剔除 _aug0 噪声副本的 190 张原始帧） |
| `eval_a1_clean190.py` | A1(无增强) vs A2(含增强) 对比——回答"增强 bug 是否毁了训练" |
| `eval_detail.py` | 量化误差细粒度分析（分层 AP/逐图 ΔAP/噪声鲁棒性） |
| `export_quant.py` | ONNX INT8 静态量化（校准集/量化粒度可控） |
| `make_figures.py` | 实验3 报告插图生成 |

### exp3/p2_check（2 个）
| 文件 | 用途 |
|---|---|
| `make_subset.py` | 生成 test190 子集清单与 data.yaml |
| `val190.py` | 用项目自己的 ultralytics 在 190 帧上验 A2（与实验2 同口径） |

### exp3/p2_delivery/scripts（约 47 个）—— 实验3 第二阶段交付链（CPU 线 + GPU 线）
| 文件 | 用途 |
|---|---|
| `bootstrap.py` | 环境引导（CPU 线强制只用 CPU） |
| `infer.py` | 推理封装：BGR→原坐标 Nx6 框（PT/ORT/OpenVINO 通用） |
| `metrics.py` | 单类 101 点 AP（与历史 SSDLite 同协议） |
| `native_val.py` | 原生框架（非导出）精度验证 |
| `eval_detail.py` | 细粒度精度评估（分层/逐图） |
| `export_fp32.py` / `export_fp16.py` / `export_quant.py` | 导出 ONNX FP32 / FP16 / INT8 量化 |
| `quant_ov_dfl.py` | OpenVINO 量化（含 DFL 头处理） |
| `bench_exp3.py` | 正式基准测试（内存 JPEG→检测框） |
| `repeat_cpu.py` / `repeat_gpu.py` / `repeat_pipeline.py` | 基准复测（多次取稳） |
| `resolution_runtime.py` / `try_resolution_cpu.py` | 分辨率-耗时权衡实验 |
| `tune_cpu.py` | CPU 执行参数调优（只看速度不碰测试标签） |
| `cpu_runtime.py` / `analyze_cpu.py` / `after_cpu.py` | CPU 执行画像与结果分析 |
| `lock_selection.py` / `runtime_lock.py` | 运行时互斥锁与配置锁定（防实验互相干扰） |
| `run_cpu.py` / `finish_cpu.py` / `finalize_results.py` | 串行跑完 CPU 链并汇总定稿 |
| `build_cpu_report.py` / `render_cpu_report.py` / `package_cpu.py` | CPU 线报告生成/渲染/打包 |
| `plot_cpu.py` / `plot_heatmap.py` | 基准图/热力图 |
| `verify_cpu.py` / `write_acceptance.py` | 复用产物核验 + 验收文档生成 |
| GPU 线 `gpu/scripts/*`：`build_trt.py`/`build_student_trt.py`（TensorRT 引擎构建）、`optimized_trt.py`（GPU 预处理+常驻缓冲优化管线）、`auto_infer.py`（GPU 优先 CPU 回退）、`distill_yolo.py`/`distill_temperature.py`/`temperature_study.py`（GPU 蒸馏与温度实验）、`bench_pipeline.py`/`eval_pipeline.py`（管线级基准/评估）、`export_student_fp16.py`（学生模型 FP16 导出）、`recommend_gpu.py`/`apply_gpu_recommendation.py`（GPU 选型建议与套用）、`smoke_train.py`（训练冒烟）、`checkpoint_metadata.py`（检查点元数据）、`complete_deployment.py`/`complete_md.py`/`finish_all.py`/`finish_temperature.py`（串行收尾）、`repeat_gpu.py`/`repeat_pipeline.py`（复测）、`verify_auto.py`/`verify_md.py`（自动核验）、`summarize_md.py`/`build_md_report.py`/`render_md_report.py`/`package_md.py`（MD 版报告与打包） | GPU 交付链对应物（同 CPU 线，跑在 GPU 上） |

### exp3_v2（5 个）—— 实验3 v2（aug0 缺陷修复后重训整链）
| 文件 | 用途 |
|---|---|
| `run_quant_chain.py` | v2 量化链（底座 A2′，全本地 CPU） |
| `eval_detail_v2.py` | v2 细粒度量化误差分析 |
| `overfit_check.py` | 过拟合检查（训练集 200 张 vs 没见过的 test190） |
| `protocol_check.py` | 协议核查（PyTorch vs ONNX FP32 差 0.1-0.2pp 的来源） |
| `make_figures_v2.py` | v2 报告插图 |

---

## D. scripts/ —— 数据工程流水线（实验1 + 动作线 + 报告填充，38 个文件）

### 01_acquire 数据采集（9 个）
| 文件 | 用途 |
|---|---|
| `download_sportsmot_hf.py` / `extract_basketball.py` | 从 HuggingFace 下 SportsMOT → 提取篮球子集 |
| `download_multisports_hf.py` | 下 MultiSports 篮球子集（门控仓库，需 token） |
| `multisports_to_yolo.py` | MultiSports 视频→抽帧+tube 框→YOLO 检测数据 |
| `multisports_to_events.py` | MultiSports GT 标注→解说事件表 CSV（动作线的地面真相） |
| `mot_to_yolo.py` | SportsMOT（MOT 格式）→YOLO 检测格式 |
| `crawl_zhibo8_livetext.py` | 爬直播吧文字直播（解说语料） |
| `crawl_basketball_news.py` | 合规爬篮球新闻（非结构化文本） |
| `extract_frames_from_video.py` | 自采视频抽帧补充工具 |

### 02_clean 数据清洗（9 个）
| 文件 | 用途 |
|---|---|
| `clean_images.py` | 图像/视频帧清洗+标注校验+元数据隐私清理 |
| `clean_texts.py` / `clean_livetext.py` | 文本语料清洗/直播语料清洗与划分 |
| `clean_multisports.py` | MultiSports 视频清洗校验 |
| `annotation_qc.py` | 标注质量审计第一关：训练模型当"第二标注员"交叉核对 |
| `annotation_qc_texture.py` | 第二关：训练自由判据（免疫模型记忆化） |
| `annotation_qc_coco.py` | 第三关：COCO 预训练权重盲裁判 |
| `annotation_qc_review.py` | 第四关：三关无法裁定时构建抽样目检集 |
| `run_dj.py` | dj-process.exe 包装启动器（本机 torch DLL 兼容修复） |

### 03_augment / 03_train / 04_standardize（5 个）
| 文件 | 用途 |
|---|---|
| `augment_images.py` | 图像增强（检测框同步几何变换） |
| `verify_aug_v2.py` | 增强修复校验（证明"图变了框跟着走"） |
| `train_yolo.py` | 实验2：训练球员检测 YOLOv8 |
| `benchmark_models.py` | 模型选型对比（CPU 速度 + person→player 迁移 mAP50） |
| `standardize_and_split.py` | 数据标准化 + 8:1:1 划分 + YOLO 目录结构 |

### 05_evaluate 数据质量评估（3 个）
| 文件 | 用途 |
|---|---|
| `quality_report.py` | Data-Centric 四维量化质量报告 |
| `plot_clean_charts.py` | 清洗前后质量对比图 |
| `plot_fig3_mechanism.py` | "清洗到底改了什么"机理构图 |

### 06_action 动作识别线（6 个）
| 文件 | 用途 |
|---|---|
| `action_classes.py` | **类别契约**：MultiSports 18 类→13 动作+背景（唯一权威定义） |
| `build_clips.py` | GT tubes→16帧×112×112 训练 clip（含部署同口径裁剪） |
| `train_action.py` | 训练 MC3D-18 动作分类模型 |
| `export_onnx.py` | 导出 ONNX（FP32+动态 INT8）并验证等价性与 CPU 延迟 |
| `smoke_worker.py` | 端到端冒烟：临时 DB+runs 跑完整 process_task |
| `package_kaggle.py` | 打 Kaggle 交接包（数据+脚本+Notebook 一键） |

### 06_report + run（6 个）
| 文件 | 用途 |
|---|---|
| `fill_exp1_report.py` / `fill_exp1_report_v2.py` | 实验1 报告自动填充（v2 按任务书 8 条逐项补齐） |
| `fix_exp1_report.py` / `fix_exp1_report_v2.py` | 实验1 报告视觉验收问题修复 |
| `gen_dataset_tree_v2.py` | 生成数据集目录结构图（图1） |
| `run/launch.py` | 启动辅助：等就绪/查端口/健康检查 |

---

## E. report/ —— 报告生成与质检（8 个文件）

| 文件 | 用途 |
|---|---|
| `build_exp5_report.py` | 实验5 九章总报告生成器（python-docx） |
| `make_loop_figure.py` | "实验1→5 全流程闭环"示意图（图 1-1） |
| `check_report.py` | 报告终检：页数/目录/图表/字体/页码/占位符 |
| `check_tables.py` | 检查表格跨页 |
| `verify_toc.py` | 解析 PDF 目录逐条核对页码 |
| `fix_toc_style.py` | 给目录补样式（右对齐制表位+点线） |
| `apply_edits.py` / `refresh_v2.py` | 实验3 报告合并稿修订 / v2 数字整链替换 |

---

## F. src/（1 个）

| 文件 | 用途 |
|---|---|
| `src/basketball_dataset.py` | PyTorch Dataset 封装（视觉检测数据集，训练侧用） |

---

## G. _归档/（45 个，已封存）

历史版本与交接包，**不影响当前系统**：`旧版Web系统/`（实验4 第一版后端）、`旧训练产物/code_reuse/`（旧检测服务代码）、`交接与压缩包/`（各阶段 share/handoff 交付包与 Kaggle 副本）、`旧构建与日志/report_build/`（旧报告构建脚本）。需要考古时再查。

---

## 30 秒理解数据流

```
SportsMOT/MultiSports 下载 → 01采集 → 02清洗(四关QC) → 03增强 → 03训练(YOLO) ──→ 实验3 蒸馏/量化/交付(选型出 a2v2 ONNX)
                                          │                                            │
直播吧文字直播 ──────────────────────→ 文本清洗 ──→ 实验4 文本分类器(joblib)            ↓
MultiSports GT ──→ 06动作(build_clips→MC3D-18→ONNX) ────────────┐   exp4/complete_web_system/backend
                                                               └──→ video_service: 检测→跟踪→动作→事件
                                                                        ↓
                                              llm.py 逐条解说 + vision 看帧 + narration_service 整场稿
                                                                        ↓
                                              tts.py 语音 MP3 + agent 对话（tools 分页查事件）→ 前端页面
```

---

> 2026-11-17 仓库整理：models 下 exp2/exp3 的 v1 训练产物与 a2_cpu_tuned、根目录 start/stop_exp5.bat 已删除（仅保留 v2 最终版，历史可溯）；本文 C 节描述的 v1 脚本如已不存在，请以 git 历史为准。
