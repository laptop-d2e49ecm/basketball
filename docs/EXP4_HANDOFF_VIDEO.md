# 实验 4 交接说明 —— 视频主线（给你的部分）

> 收件人：视频主线负责人。你的实现范围 = 你的《前端后端架构设计.md》v2 全部内容，
> 按 v2 实现即可；本文只补充 4 件东西：**① 双方必须共同遵守的契约（对任务书硬性要求的适配）；
> ② 两个模型文件（含指标口径）；③ 可直接复用的代码件（已冒烟验证）；④ 联调素材与对接点**。
> 总体方案见包内 `EXP4_PLAN.md`（v3.1，已标注双方分工）。

---

## 0. 一分钟速览

| | 你负责 | 我负责 |
|---|---|---|
| 前端 | Vue3+Ant Design Vue 骨架、路由、NavBar、**视频分析页**（上传/进度/回放叠加/解说面板）、Pinia、WS 客户端 | **球员检测页 / 解说文本分类页 / 图文匹配页** 三页（以组件形式挂进你的骨架） |
| 后端 | `tasks`/`meta` API、WebSocket `/ws/task/{id}`、SQLite 任务表、**Worker 进程**（解码→track→事件→解说桩→落盘→耗时实测） | `/api/v1/detect`、`/api/v1/text/classify`、`/api/v1/match` 三 API + 统一信封/异常体系 + 文本分类器训练 |
| 模型 | `best.pt`（视频 track 用，ByteTrack 依赖 ultralytics） | `a2_int8_val346.onnx`（图像检测 API 用，实验3优化模型） |

---

## 1. 必须共同遵守的契约（相对你 v2 文档的 4 处修订）

你 v2 的架构判断（SQLite 持久化、独立 Worker、REST+WS 分工、能力边界声明）全部保留，只需按任务书做以下适配：

### 1.1 REST 路径加版本前缀 `/api/v1`（任务书"API 设计规范"）

你文档中的 `/api/tasks` → `/api/v1/tasks`，其余同理。WS 路径不变（`/ws/task/{id}`）。

### 1.2 REST 统一响应信封 `{code, result, msg}`（任务书"数据格式规范"原文）

```jsonc
// 成功
{ "code": 0,   "result": { "task_id": "..." }, "msg": "ok" }
// 失败（前端 Axios 拦截器读 code/msg 弹友好提示）
{ "code": 400, "result": null, "msg": "视频格式错误，请上传 MP4/MOV/AVI" }
```

错误码表（全局异常 handler 统一产出，前端不用逐接口处理）：

| code | 场景 | 示例 msg |
|---|---|---|
| 400 | 输入错误（扩展名/超限/损坏/空文本） | 图像格式错误，请上传 PNG/JPG |
| 404 | 资源不存在（task_id 无效/路径打错） | 任务不存在 |
| 500 | 模型/服务器错误 | 模型推理失败，请稍后重试 |

异常体系代码在 `code_reuse/errors.py`，直接拷走挂到 FastAPI 即可（用法见文件尾注释）。

### 1.3 UI 库用 Ant Design Vue（不用 Element Plus）

任务书实验环境明确写 "Ant Design（UI组件库）"。Vue 3 本身任务书允许（"React 19+（或 Vue 3+）"），
但 UI 库建议对齐字面要求：`npm i ant-design-vue@4`，上传/进度/表格组件覆盖度与 Element Plus 同级，迁移成本就是改组件名。

### 1.4 检测框坐标契约（重要，实验 1 踩过坑）

**所有框数据（REST 与 detections.jsonl）一律归一化 cx,cy,w,h ∈[0,1]**，响应里随带画布尺寸：

```jsonc
{ "cx": 0.5, "cy": 0.61, "w": 0.03, "h": 0.12, "conf": 0.87, "track_id": 3 }
```

> 背景：实验 1 做数据增强时，像素/归一化坐标混用一次，所有框被"压成一个点"，排查了很久。
> 修复经验固化为两条纪律：**① 换算只允许在一个工具函数里做；② 换算结果必须过合法性断言**（∈[0,1] 且 w,h>0）。
> 你的回放叠加（`<video>`+canvas）正是同类高发区，建议：
> - 前端只写一个 `denormBox(box, canvasW, canvasH)` 工具函数（`code_reuse/coords.py` 是后端同款逻辑，可对照翻译成 TS）；
> - canvas 内部尺寸 = video 元素显示尺寸 × devicePixelRatio，框坐标 = 归一化 × canvas 内部宽高（**不是** video 原始分辨率，也不是 CSS 尺寸——两者混用必错位）；
> - 加一条 vitest：归一化→像素→归一化往返误差 < 1e-6。

---

## 2. 模型文件（`weights/`）

| 文件 | 用在哪 | 参数量 | 体积 | test mAP50 | 备注 |
|---|---|---|---|---|---|
| `best.pt` | 你的 Worker track 模式（`YOLO('best.pt').track(...)`） | 3.2M | 6.5MB | 0.419 | 实验 2 A2 部署选型（增强数据 4316 张训练） |
| `a2_int8_val346.onnx` | 我的图像检测 API | 3.13M | 3.6MB | 0.420 | 实验 3 INT8 静态量化首选部署版（val346 校准），任务书"集成实验3优化模型"的落点 |

实测参考（2026-11-01，Ryzen 7 6800H CPU，含 letterbox 预处理，单张 640×640）：
ONNX INT8 单帧推理 **约 130–160ms**——图像线端到端远低于任务书"前端展示≤2 秒"合格线。
你的视频基线（每帧 ms / 端到端 / FPS）按 v2 的 M1 验收项实测，`frame_step=1` 起步。

口径提醒（报告"关联分析"素材）：图像 API 用实验 3 优化模型（INT8，3.6MB）；
视频 Worker 用实验 2 原始 best.pt——因为 track 模式依赖 ultralytics 内置 ByteTrack，
ONNX 无跟踪器。两模型同源（A2 权重量化前后），精度差 ≤0.001 mAP50，报告中如实说明即可。

---

## 3. 可复用代码件（`code_reuse/`，已冒烟验证，可直接拷进你的工程）

| 文件 | 作用 | 依赖 | 集成方式 |
|---|---|---|---|
| `detector.py` | ONNX INT8 检测封装：letterbox（与实验 3 infer.py 同口径，含舍入细节）+ numpy NMS（**免 torch**）+ 出画/过小框过滤计数 + 归一化输出 | onnxruntime, pillow, numpy | 拷到你的 `app/services/`，改一下文件头相对导入（`from ..core import ...` → 你的包路径）即可 |
| `coords.py` | 归一化↔像素换算唯一实现 + 合法性断言（防"压成一点"） | numpy | 后端侧用；翻译成 TS 给前端 |
| `errors.py` | InputError/NotFoundError/ModelError + 全局 handler 注册函数 | fastapi | `main.py` 里 `register_exception_handlers(app)` |
| `schemas.py` | Pydantic 契约：统一信封、检测/文本/匹配结果、**任务表视图（与你的 SQLite 字段对齐）** | pydantic | 参考字段命名，保持双方一致 |
| `preprocess.py` | 实验 1 清洗规则服务化：扩展名白名单、大小限制、PIL 损坏检测、空文本校验 | pillow | 上传入口统一调用 |

冒烟记录（`detector.py`，实验 1 test 划分，conf=0.25/iou=0.55）：
`f000005.jpg` 我 10 框 vs ultralytics FP32 9 框（IoU 均值 0.874）、`f000025.jpg` 10 vs 10（0.940）、
`f000040.jpg` 9 vs 9（0.926）；坐标全部 ∈[0,1]，dropped_boxes=0。差异属 INT8 量化级别。

---

## 4. 联调素材（`samples/`）

- `demo_video.mp4`：MultiSports 篮球段（2.4MB，720p）——跑你 Worker 全流程与基线实测用；
- `images/`：实验 1 **test 划分**抽样 8 张（含标注框最多的 3 张，GT 框数写在文件名后的 txt 同目录）——图像检测页联调用（**只用 test 划分，别拿 train 图演示**，防泄漏纪律）；
- `texts/解说样例.jsonl`：test 划分抽 20 条解说——文本分类页联调用（字段：game_id/live_time/text/commentator/score）。

---

## 5. 对接点与里程碑

| 时点 | 对接内容 |
|---|---|
| 你开工前 | 本包 = 契约定稿：schemas 字段名、信封、错误码、坐标契约、WS 消息格式（你 v2 §5 原样） |
| 骨架就绪后 | 我把三页组件挂进你的路由（约定路由 `/detect` `/text` `/match`，你的视频页用 `/video`）；NavBar 四项 |
| 我的 `/api/v1/detect` 就绪前 | 你可先按 schemas mock；就绪后 Postman 集合（我出）直接导入测 |
| M1（你的基线验收） | 把每帧 ms/端到端 s/FPS 发我，汇入报告性能表 |
| 合并 | 最终统一打 `实验4_前后端完整代码模型与报告.zip`（报告章节分工见 EXP4_PLAN.md §八） |

## 6. 常见坑（本仓库实验 1-3 真实踩过，直接绕行）

1. **CORS**：FastAPI `CORSMiddleware` 放行 `http://localhost:5173`；Vite 里再配 `server.proxy` 把 `/api`、`/ws` 转发到 8000，双保险（WS 代理需 `ws: true`）。
2. **Windows + uvicorn**：`uvicorn app.main:app --port 8000 --reload`；Worker 另开终端 `python -m worker.main`。
3. **torch DLL 崩溃（WinError 1114）**：若本机曾装 Anaconda，其 2020 版 `msvcp140.dll` 会先加载导致 torch 崩溃——用 venv 且避免从 Anaconda Prompt 启动；崩溃签名看 Windows 事件日志（实验 1 排查记录在 `docs/CLEANUP_LOG.md`）。
4. **Kaggle/云端不需要**：本实验全部本地 CPU 可完成；Celery 是任务书要求的可选线（`TASK_BACKEND=celery` + `docker run -p 6379:6379 redis`），默认你的 Worker+SQLite 模式即为演示模式，报告双模式说明。
