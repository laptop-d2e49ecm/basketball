# 实验 4 方案：前后端开发（AI 球员检测与解说 Web 系统）v3 合并版

> 依据：`实验4任务书.pdf`（5 页全文核对）+ `AI全栈开发实验报告模板-2026-4.doc` + 本仓库实验 1/2/3 实际产出 + 组内《前端后端架构设计.md》（v2，视频主线）。
> **v3.1 分工确定（2026-11-01）**：**视频主线（前端骨架+视频页+任务/WS/SQLite+Worker）由队友按其《前端后端架构设计.md》v2 自行实现**；**本侧负责三核心页、检测/文本/匹配三 API、文本分类器训练**，并提供已冒烟验证的共享契约件（统一信封/异常体系/坐标换算/上传校验/ONNX 推理封装，随交接包交付）。双方共同遵守本文档第二、三节契约；交接说明见 `docs/EXP4_HANDOFF_VIDEO.md`。
> v3 合并要点（保留）：以 v2 视频主线为骨架，按任务书补齐三核心页、实验3 INT8 模型集成、文本分类与图文匹配工作流、Celery 可选模式、`/api/v1` 版本化与统一信封、Ant Design Vue。

---

## 一、任务书要求 vs 本项目映射

| 实验 1 数据线 | 任务书页面 | 本方案页面 |
|---|---|---|
| 检测图像（SportsMOT→YOLO 640×640） | 图像分类页 | **球员检测页**：上传图→实验3 INT8 模型→归一化框+人数+置信度+耗时 |
| 解说文本（40,376 条）+资讯 120 篇 | 文本分类页 | **解说文本分类页**：输入文本→动作事件分类（弱监督训练） |
| 图文一致性判定 | 多模态匹配页 | **图文匹配页**：图+文→检测 API→文本 API→一致性（FastAPI 依赖注入串联，任务书 4.2.3 工作流） |
| 视频（MultiSports 526 段） | （任务书之外） | **视频分析旗舰页**（v2 主线）：上传视频→异步检测→回放叠加框+解说字幕，实验 5 直接受益 |

模型分工（报告"关联分析"素材）：

| 模型 | 体积 | test mAP50 | 用在哪 |
|---|---|---|---|
| `a2_int8_val346.onnx`（实验3首选部署版） | **3.6MB** | **0.420** | 图像检测 API（任务书"集成实验3优化模型"的直接落点） |
| `A2 best.pt`（实验2部署选型） | 6.5MB | 0.419 | 视频 Worker track 模式（ByteTrack 依赖 ultralytics 内置跟踪器），实测基线后可评估切 INT8 |

任务书其余硬性要求落点：React 19 **或 Vue 3+**（选 Vue 3+Ant Design Vue+Vite+TS）；响应式 Grid 三断点；Chrome/Safari/Firefox 测试矩阵；RESTful `/api/v1` 名词路径+`/docs` 自动文档；Celery+Redis 异步（可选模式）；CORS 白名单；错误码 400/404/500；性能"前端展示≤2 秒"。

---

## 二、总体架构与数据流

```
┌─ 前端 SPA Vue3 + Ant Design Vue + Pinia + Axios (localhost:5173) ────┐
│ NavBar → /detect 球员检测页  /text 解说文本分类页  /match 图文匹配页   │
│          /video 视频分析页（上传→进度→回放：<video>+canvas 叠框+解说） │
└──────┬──────────────────────────── REST /api/v1 ─┬─ WS /ws/task/{id} ─┘
       ▼                                     ▼
┌─ API 进程 FastAPI :8000 ────────────────────────────────────────────┐
│ 统一信封 {code,result,msg} · CORS · 异常体系(400/404/500)             │
│ detect(ONNX INT8 单例) · text(joblib) · match(依赖注入串联) · tasks   │
│ SQLite 任务表(WAL)：pending→running(阶段/进度)→ready/failed          │
└──────┬──────────────────────────────────────────────────────────────┘
       │ 认领任务（默认：独立 Worker 进程轮询；可选：Celery+Redis 分发）
┌──────▼──────────────────────────────────────────────────────────────┐
│ Worker：OpenCV 解码抽帧 → best.pt track 检测 → detections.jsonl      │
│  → 轨迹启发式事件 events.jsonl(source=heuristic) → 解说桩文案         │
│  → 逐帧耗时实测写回任务表（采样决策依据）                             │
└──────────────────────────────────────────────────────────────────────┘
```

图像线数据流（任务书"重点关注"原文的落点）：用户输入→表单校验→Axios POST（图像 multipart/form-data、文本 application/json）→FastAPI 接收→**实验1预处理复用**（损坏/EXIF 校验、640×640 letterbox、出画框过滤计数）→**实验3 INT8 推理**→统一 JSON→前端渲染（框经 coords 工具换算画布）。

---

## 三、后端设计（队友：任务/WS/Worker；本侧：检测/文本/匹配）

```
exp4/backend/
├── app/
│   ├── main.py              # FastAPI、CORS、lifespan 加载 ONNX/文本模型、挂静态托管
│   ├── core/                # config / errors(400/404/500) / schemas(Pydantic 契约) / coords(坐标唯一实现)
│   ├── api/                 # detect.py / text.py / match.py / tasks.py / meta.py
│   ├── ws/task_ws.py        # WebSocket：阶段/进度/解说事件/完成通知（纯 JSON）
│   └── db/                  # database.py(SQLite WAL) / task_repo.py(CRUD，API 与 Worker 共用)
├── worker/                  # main.py(轮询认领) / video_service.py(解码+track+耗时) /
│                            # event_service.py(启发式事件) / commentary/(stub 桩，实验5可插拔 LLM)
├── celery_app.py            # TASK_BACKEND=celery 时的等价任务（复用 worker.video_service）
├── preprocess.py            # 复用实验1：图像校验 + letterbox + 框过滤（dropped_boxes 计数）
├── train_text_clf.py        # 实验1语料 → 弱监督动作分类 → joblib
├── weights/{a2_int8_val346.onnx, best.pt}
├── ml/text_action_clf.joblib + text_clf_meta.json
├── runs/{task_id}/          # 原视频 · detections.jsonl · events.jsonl（按时间范围回读）
├── tasks.db                 # SQLite
├── tests/                   # pytest：坐标往返/契约/异常路径/任务状态机
├── postman_collection.json / requirements.txt
```

### REST API（/docs 自动生成；统一信封 `{code,result,msg}`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 模型加载状态、后端模式（worker/celery）、版本 |
| POST | `/api/v1/detect` | multipart 图像(+conf/iou)→归一化框+人数+dropped_boxes+infer_ms |
| POST | `/api/v1/detect/batch` | ≤20 张→task_id（异步） |
| POST | `/api/v1/text/classify` | json {text}→动作类别+置信度+top3 |
| POST | `/api/v1/match` | multipart 图像+文本→双侧证据+match 结论（依赖注入串联 detect→text） |
| POST | `/api/v1/tasks` | multipart 视频(+可选队名/比分)→task_id |
| GET | `/api/v1/tasks/{id}` | 状态/阶段/进度/实测耗时 |
| GET | `/api/v1/tasks/{id}/detections?t_start&t_end` | 按时间范围读框（回放/拖动免重算） |
| GET | `/api/v1/tasks/{id}/events` | 事件与解说列表（source 分级） |
| GET | `/api/v1/tasks` | 历史任务（SQLite） |
| GET | `/api/v1/meta/model` | 模型参数量/mAP/类别/实测耗时（无估算值） |

WebSocket `/ws/task/{id}`：`{type: progress|commentary|done|failed, ...}`，与 v2 契约一致。

### 异常体系与跨域

`InputError→400`（非图像/超 10MB/空文本）、`NotFoundError→404`（任务不存在）、`ModelError→500`；全局 handler 统一信封；前端 Axios 拦截器读 msg 弹友好提示。CORS 开发环境允许 `localhost:5173`。

### 异步任务双模式（任务书 Celery 要求 + v2 工程判断的折中）

- **默认 `worker`**：独立进程轮询 SQLite 认领（v2 设计，零外部依赖，演示最稳）；
- **可选 `celery`**：`TASK_BACKEND=celery` + `docker run redis` 后，任务经 Celery+Redis 分发，处理函数与 Worker 完全复用同一 `video_service`；README 给两条启动命令，报告对比两模式定位（单机演示 vs 分布式扩展）。

### 视频 Worker 能力边界（v2 §3.4 全文沿用）

现有模型只提供单类 `player` 框；track_id 仅轨迹标识。事件分 `source=heuristic`（人数变化/篮下聚集/方向突变）与 `source=action_model`（实验 5 预留）；解说桩只输出泛化文案，**不出现"7 号球员/蓝队/比分"等模型不存在的信息**，队名比分仅来自用户表单；界面标注"AI 生成，供复核"。

---

## 四、前端设计（队友：骨架+视频页；本侧：三核心页挂载）

```
exp4/frontend/src/
├── views/       DetectView / TextView / MatchView / VideoView（上传/进度/回放三态）
├── components/  NavBar / DataInput / ErrorAlert / TaskProgress /
│                DetectionPlayer(<video>+canvas 叠框) / CommentaryPanel / ModelInfoCard
├── stores/task.ts        # Pinia 任务状态机 + WS 连接
├── api/client.ts         # axios 实例+拦截器（信封解包、错误弹窗）
├── api/coords.ts         # 归一化↔画布像素 唯一换算点（+ vitest 往返测试）
└── types/                # 与后端 schemas 对齐
```

- 响应式：AntD Vue Grid（xs/md/xl），移动端上传区全宽；只用 Flex/Grid，不引 Polyfill；
- 检测页：Canvas 原生分辨率画框（CSS 等比缩放），统计卡（人数/耗时/dropped_boxes）；
- 视频页：上传→WS 进度→回放 `requestAnimationFrame` 按 currentTime 取框叠加，解说面板点击定位；
- 测试矩阵：Chrome（主力）/Safari（WebKit）/Firefox。

---

## 五、坐标系防线（实验 1 增强教训的制度化）

实验 1 踩坑：像素/归一化坐标混用把框压成一点，靠"显式互转+出画/过小框按阈值丢弃并计数"修复。实验 4 同类高发区在前后端坐标链路，设四道防线：

1. **契约固化**：REST 一律返回归一化 cx,cy,w,h∈[0,1]，并随带 image_w/image_h（视频框随带归一化坐标+帧时间戳）；
2. **单一实现**：后端 `app/core/coords.py`、前端 `api/coords.ts` 是各自唯一换算点（处理 letterbox/等比缩放偏移）；
3. **单测往返**：pytest/vitest 断言归一化↔像素往返误差 <1e-6、坐标∈[0,1]、w/h>0（防"压成一点"回归）；
4. **过滤计数**：出画/过小框（<8px）按实验 1 规则丢弃，`dropped_boxes` 字段回显界面。

演示样例一律取实验 1 **test** 划分（图像 380 张抽样、解说取 split_test），延续防泄漏纪律。

---

## 六、测试与性能口径

| 项 | 方法 | 标准 |
|---|---|---|
| API 功能 | Postman 集合（实验1 test 样例调用示例） | 全接口符合信封与错误码表 |
| 异常路径 | 非图像/超限/空文本/坏任务 ID | 400/404/500 + 友好 msg |
| 跨平台 | Chrome/Safari/Firefox 逐页点检表 | 三页+视频页布局功能一致 |
| 图像性能 | 前端计时提交→渲染，10 次均值/P95 | ≤2s 合格（INT8 CPU 单帧几十 ms 级，预计大幅低于） |
| 视频基线 | 演示 mp4 全流程：每帧推理 ms/端到端 s/处理 FPS | 写回任务表，作 frame_step/插值决策依据（v2 M1 验收） |
| 端到端 | 四页各 1 闭环用例 | 截图入报告 |

---

## 七、分工与时间线（6 学时+课外）

| | 队友（视频主线，按 v2 设计实现） | 本侧 |
|---|---|---|
| 课前 | Vite+Vue3+AntD Vue 脚手架、四页路由骨架、SQLite+Worker 骨架 | ONNX 推理封装（已冒烟）、文本分类器训练、契约件定稿 |
| 阶段1（3学时） | 视频页三态 UI、tasks/meta API、WS 通道 | 检测/文本/匹配三页 UI+交互（挂进她的骨架） |
| 阶段2（3学时） | Worker 全流程（解码→track→事件→解说桩）+ 回放叠加 | 三 API+信封+异常接入 main、CORS、Postman、pytest |
| 课后 | 视频基线实测（每帧 ms/端到端 s/FPS） | 图像性能实测（≤2s）、跨浏览器矩阵、报告 API 表/架构图 |
| 合写 | 报告：目的/环境/分工/问题与解决/总结展望 | |

时序依赖一处：**契约件（schemas/信封/错误码/coords，随交接包给出）先定稿**，队友按契约在其骨架内实现任务线；本侧三 API 就绪前，前端以 Postman/mock 数据并行。

---

## 八、报告章节对照（模板 2026-4）

| 模板章节 | 填什么 |
|---|---|
| 一 目的 | 数据-模型-应用闭环（实验1数据→实验3模型→Web 应用） |
| 二 环境 | Vue3/AntD Vue/Vite；FastAPI/Uvicorn/ONNX Runtime/SQLite/Celery(可选)/Docker(可选) |
| 三 内容与步骤 | 4.1 前端四页+公共组件+响应式兼容；4.2 后端架构/API/工作流/异步双模式/集成联调 |
| 四 关键技术与难点 | 跨域、坐标契约（引实验1教训）、WS 进度与回放按时间范围读框、Worker/API 进程分离、Celery 双模式 |
| 五 结果与分析 | 架构图+数据流、API 文档表+调用示例、错误码表、跨平台测试表、图像性能（≤2s）+视频基线 |
| 六 总结与展望 | 实验 5：action_model 事件通道 + CommentaryService 换 LLM 实现 |
| 七 参考文献 | React/FastAPI/RESTful/Celery/Vue 官方文档 |

---

## 九、要分享的目标文件（share_exp4 包）

```
share_exp4/
├── README.md                  # 5 分钟跑通（后端 venv/uvicorn/worker；前端 pnpm i/dev；演示脚本）
├── backend/                   # 上述后端全量源码 + requirements.txt + tests + postman
│   ├── weights/a2_int8_val346.onnx (3.6MB) + best.pt (6.5MB)
│   └── ml/text_action_clf.joblib + meta
├── frontend/                  # Vue3 源码（不含 node_modules，附 pnpm-lock/package-lock）
├── samples/                   # 实验1 test 抽样图 10-20 张 + 解说样例 20 条 + 演示 mp4 1 段
├── docs/EXP4_PLAN.md + 前端后端架构设计.md
├── test/跨平台测试记录 + 截图
├── report/实验4报告.docx / .pdf
└── 数据集下载链接.txt
```

打包名：`实验4_前后端完整代码模型与报告.zip`（预计 <60MB，含 6.5MB best.pt 与演示视频）。

---

## 十、执行进度（2026-11-01 更新）

| 部分 | 负责人 | 状态 | 关键产出 |
|---|---|---|---|
| 契约件（信封/异常/坐标/校验/ONNX 封装） | 本侧 | ✅ 完成 | `exp4/backend/app/core|services/`，已随交接包发给视频主线 |
| 文本动作分类器 | 本侧 | ✅ 完成 | 40,376 条语料 → 10 类，留出集 acc 0.9968（弱监督规则一致性口径）；域判定=规则命中 OR prob≥0.5 |
| 三 API（detect/text/match + batch 异步 + health/meta） | 本侧 | ✅ 完成 | `exp4/backend/`，pytest 14 项全绿 |
| 性能实测 | 本侧 | ✅ 完成 | `exp4/bench_results.json`：检测 e2e 均值 132.8ms/P95 137.1ms、文本 7.9ms、匹配 139.0ms（合格线 2000ms） |
| 前端三核心页 | 本侧 | ✅ 完成 | `exp4/frontend/`：Vue3+AntD Vue，vite build 通过，vitest 坐标契约 2 项全绿，经 5173 代理联调全链路通过 |
| Postman 集合 | 本侧 | ✅ 完成 | `exp4/backend/postman_collection.json`（11 请求含正反用例） |
| 前端骨架+视频页 | 队友 | ✅ 完成 | `exp4/complete_web_system/frontend/`：四页+Pinia+WS 客户端+Playwright e2e（24 项过） |
| tasks/WS/SQLite/Worker | 队友 | ✅ 完成 | `exp4/complete_web_system/backend/`：任务 API+WS+SQLite+Worker（track/事件/解说桩/耗时落库）+Celery 双模式（commit c555f28，2026-11-02） |
| 模型完整性核验 | 本侧 | ✅ 完成 | SHA256 校验：onnx/best.pt/joblib 与原始权重逐字节一致（`models/SHA256SUMS.txt`） |
| Firefox 浏览器测试 | 队友 | ⬜ 缺 | Playwright 已配置 firefox 项目，但 VERIFIED_TESTS 无运行记录（任务书要求三浏览器） |
| 视频基线实测 | 双方 | ⬜ 缺 | 机制就绪（avg_infer_ms/total_seconds 落库），需用 36s 演示视频跑一次出数；另 samples/demo_video.mp4 仍是旧 2s 版需更换 |
| Celery 模式实测 | 队友 | ⬜ 可选 | 代码就绪（worker/celery_tasks.py），需 Redis；报告如实写双模式设计即可 |
| 跨平台浏览器测试矩阵 | 双方 | ⬜ 部分 | Chromium(Edge)+WebKit 已过，补 Firefox 即齐 |
| 报告 + 最终打包 | 合写 | ⬜ | `实验4_前后端完整代码模型与报告.zip`（章节映射见 §八） |
