# 篮球赛事视频分析系统

本文件集中说明前端、后端的安装、启动、使用、接口和测试方法。以下命令以 Windows PowerShell 为例，项目根目录指同时包含 `frontend/`、`backend/` 和启动文件的目录。

系统支持上传篮球比赛视频、查看分析进度、回放检测框、按事件时间定位画面，以及球员图像检测、解说文本分类和图文篮球相关性检查。

## 1. 快速启动与关闭

首次使用先完成第 2 节的环境准备。已经安装好依赖后：

1. 双击根目录的 **`start_project_v3.bat`**。
2. 等待后端、视频 Worker 和前端服务准备完成，浏览器会自动打开视频分析工作台。
3. 上传 MP4，点击“上传并分析”，等待进度完成后查看结果。
4. 使用结束后双击 **`stop_project.bat`**，关闭启动器管理的服务。

启动器在后台运行所需服务，无需手动打开三个 PowerShell 窗口。两个 BAT 文件已内置启动和停止逻辑，不依赖独立的 PS1 文件。仅关闭浏览器不会停止服务；手动启动的服务需在原终端按 `Ctrl+C` 停止。

| 入口 | 地址或位置 |
|---|---|
| 系统首页 | http://127.0.0.1:5173/ |
| 球员图像检测 | http://127.0.0.1:5173/detect |
| 解说文本分类 | http://127.0.0.1:5173/text |
| 图文匹配 | http://127.0.0.1:5173/match |
| 后端接口调试文档 | http://127.0.0.1:8000/docs |
| 后端健康检查 | http://127.0.0.1:8000/api/v1/health |
| 启动日志 | `.runtime/logs/` |

默认使用独立 Worker 模式，不需要 Redis 或 Docker。运行前请停止此前手动启动的服务，避免占用 8000、5173 端口。

## 2. 首次安装

### 2.1 环境要求

- Windows，Python 3.11 或 3.12。
- Node.js 20.19+ 或 22.12+，以及 pnpm。
- 为依赖、模型、上传视频及兼容预览保留足够磁盘空间。
- CPU 可以运行全部功能。视频 Worker 在 CUDA 可用时选择 GPU，否则使用 CPU；图片检测使用 ONNX Runtime CPU。

“电脑有显卡”不等于当前 Python 环境能使用 CUDA，还取决于显卡、驱动和 PyTorch 安装情况。当前一键启动不负责安装依赖。

### 2.2 安装后端依赖

在项目根目录打开 PowerShell：

```powershell
py -3.12 -m venv .\backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-dev.txt
```

如果安装的是 Python 3.11，将第一条命令中的 `-3.12` 改为 `-3.11`。如果已有可用的 `backend/.venv`，无需重新创建。这里直接调用虚拟环境中的 Python，不需要执行激活脚本。

`requirements-dev.txt` 包含运行依赖及后端测试工具；仅运行时也可安装 `backend/requirements.txt`。视频预览转换依赖 `imageio-ffmpeg`，已列入运行依赖。

### 2.3 安装前端依赖

仍从项目根目录开始：

```powershell
Set-Location .\frontend
pnpm install
Set-Location ..
```

安装完成后即可使用第 1 节的一键启动方式。

### 2.4 模型文件

确认以下文件存在：

| 文件 | 用途 |
|---|---|
| `backend/weights/best.pt` | 视频中的球员检测与跟踪 |
| `backend/weights/a2_int8_val346.onnx` | 单图、批量图片及图文模块的球员检测 |
| `backend/app/ml/text_action_clf.joblib` | 解说文本分类及图文模块的文本判断 |
| `backend/app/ml/text_clf_meta.json` | 文本分类标签、领域判断规则和阈值 |

文本模型与元数据文件应配套保存。健康接口返回 `image_detector_loaded` 和 `text_classifier_loaded` 等加载状态。图片或文本模型缺失时，API 仍可启动，依赖该模型的功能会提示不可用；视频分析另外依赖 `best.pt` 和视频 Worker 正常运行。

## 3. 页面使用方法

### 3.1 视频分析

1. 在比赛画面区域选择 MP4 文件，可填写视频名称；名称为空时使用原文件名。
2. 点击“上传并分析”。页面显示“正在分析中，请稍等”和实际任务进度。
3. 完成后查看比赛画面、球员检测框、关键事件和场上人数变化图。
4. 点击事件节点，视频会暂停并定位到对应时间；点击播放器的播放键后继续播放。
5. 使用检测框开关控制框的显示，原视频内容不会因此改变。

默认单个视频最大 5 GiB。上传后由后端保存文件并创建任务，推理在独立进程执行。处理耗时受视频长度、分辨率、设备和抽帧间隔影响。

### 3.2 历史任务与清除当前任务

- 比赛画面的“历史任务”和公共导航中的最近任务入口可以打开任务列表；切换到其他功能页面后仍可查看。
- 打开历史任务可以重新加载视频和分析结果。
- 已完成或失败的任务支持删除；待处理和处理中的任务禁止删除。
- 删除历史任务会移除任务记录及其本地视频、检测结果等文件。
- “清除当前任务”只清空当前页面的预览、事件、检测框和图表，以便重新上传；它保留历史记录，也不会取消已经提交到后端的任务。

### 3.3 球员图像检测

进入“球员图像检测”，上传 PNG/JPG 图片并执行检测，查看人数、检测框、置信度和耗时。单张图片最大 10 MiB；批量 API 最多接受 20 张图片。检测页当前不提供点击图片放大的功能。

### 3.4 解说文本分类

输入 1～2000 字解说文本并提交。页面显示类别、是否属于篮球相关文本、置信度及候选分类。分类结果描述输入文字，不代表系统从视频或图片中识别出了同一动作。

### 3.5 图文匹配

同时上传图片并输入解说文本，查看两侧的判断及汇总结果。结果图片可点击放大预览。

该模块判断“图片中检测到球员，且文字属于篮球相关内容”。它不计算图文语义相似度，也不验证图片中的动作与文字描述一致。例如，文字被分类为“投篮”，并不表示图片中的球员正在投篮。

### 3.6 视频播放兼容性与解说范围

新上传视频使用浏览器本地文件预览，能否播放取决于浏览器对视频编码的支持。历史任务通过后端预览接口播放，必要时后台转换为 H.264/AAC 兼容预览。转换不改变用于推理的原始视频。

视频事件由人数变化、球员聚集和群体移动方向变化等启发式规则生成。当前不识别球体、投篮、进球、球员姓名或比分，也未接入大模型自由解说。

## 4. 前后端结构

| 部分 | 实现与职责 |
|---|---|
| 前端框架 | Vue 3、TypeScript、Vite、Vue Router、Ant Design Vue、Pinia |
| 视频工作台 | 通过 Vue 页面嵌入独立 HTML；使用 Fetch、WebSocket 和 canvas 完成任务交互与检测框绘制 |
| 图片、文本和图文页面 | Vue 组件，使用 Axios 调用 API |
| 后端 API | FastAPI、Uvicorn；文件校验、模型服务、任务管理及 REST/WebSocket 接口 |
| 视频处理 | 独立 Worker，Ultralytics 与 ByteTrack 执行球员检测和跟踪 |
| 模型运行 | 图片使用 ONNX Runtime；文本使用 scikit-learn/joblib；视频使用 PyTorch |
| 数据存储 | SQLite 保存任务状态，任务目录保存视频、检测结果和事件 |
| 可选异步队列 | Celery + Redis，复用视频处理服务 |

视频数据流：上传 MP4 → API 保存文件并登记任务 → Worker 解码、抽帧、检测和跟踪 → 写入 `detections.jsonl` 与 `events.jsonl` → 前端读取状态及结果，按播放时间绘制检测框。

任务状态为 `pending`、`running`、`ready` 或 `failed`。默认每 2 帧处理 1 帧，结果保留原始视频帧号和时间戳；进度中的帧数指实际推理的采样帧数。

前端开发服务器将 `/api` 和 `/ws` 代理至 `127.0.0.1:8000`。后端 CORS 白名单包含 `http://localhost:5173` 与 `http://127.0.0.1:5173`。

## 5. 目录与运行数据

```text
项目根目录/
├── README.md                      安装、开发、启动和使用说明
├── start_project_v3.bat            一键启动
├── stop_project.bat                关闭服务
├── frontend/
│   ├── src/                       Vue 页面、路由、导航和 API 调用
│   ├── public/                    视频工作台页面及静态资源
│   ├── e2e/                       浏览器自动化测试
│   ├── package.json               前端依赖与命令
│   └── vite.config.ts             开发服务与代理配置
├── backend/
│   ├── app/                       API、配置、数据库及模型服务
│   ├── app/ml/                    文本模型与元数据
│   ├── worker/                    独立 Worker 与 Celery 入口
│   ├── weights/                   视频和图像模型
│   ├── tests/                     后端测试
│   ├── requirements.txt           运行依赖
│   ├── requirements-dev.txt       运行及测试依赖
│   ├── requirements-celery.txt    可选队列依赖
│   ├── tasks.db                   运行后生成的任务数据库
│   └── runs/                      运行后生成的任务文件
└── .runtime/logs/                 启动器服务日志
```

每个任务的文件保存在 `backend/runs/{task_id}/`，包括原视频 `source.mp4`、检测记录和事件记录。运行数据不属于源码。备份历史任务时，应同时保留数据库和对应任务目录。

交接包的样例通常放在 `samples/`；当前本地工作区的样例位于 `share_exp4_handoff/samples/`。完整交接包还提供 `backend/postman_collection.json`，可导入 Postman 调试；本地目录未附带该文件时，可以直接使用 `/docs` 调试接口。

## 6. 后端接口

完整参数定义和在线调试入口为 http://127.0.0.1:8000/docs 。JSON REST 接口使用统一结构：成功时 `code=0`，结果放在 `result` 中；失败时 `code` 为 HTTP 状态码，`result=null`，`msg` 给出原因。视频预览返回媒体流，不使用 JSON 信封。

| 方法 | 路径 | 作用及主要参数 |
|---|---|---|
| GET | `/api/v1/health` | 服务状态、模型加载状态、后端模式、版本及抽帧间隔 |
| GET | `/api/v1/meta/model` | 模型信息、权重可用性和已记录的推理耗时 |
| POST | `/api/v1/detect` | 图片检测；表单 `file`、`conf`、`iou` |
| POST | `/api/v1/detect/batch` | 批量检测；表单 `files`，1～20 张图片 |
| GET | `/api/v1/batch/{task_id}` | 批量检测进度和结果 |
| POST | `/api/v1/text/classify` | 文本分类；JSON 字段 `text` |
| POST | `/api/v1/match` | 图文相关性检查；表单 `file`、`text`、`conf` |
| POST | `/api/v1/tasks` | 上传 MP4；表单 `file`，可选 `video_name`、`team1`、`team2`、`score1`、`score2`；HTTP 202 返回任务信息 |
| GET | `/api/v1/tasks` | 任务列表；`limit` 默认 50、最大 200，`offset` 默认 0 |
| GET | `/api/v1/tasks/{task_id}` | 状态、阶段、进度、帧数、耗时及错误 |
| DELETE | `/api/v1/tasks/{task_id}` | 删除已完成或失败的任务；处理中返回 409 |
| GET | `/api/v1/tasks/{task_id}/detections` | 检测记录；`t_start` 默认 0，`t_end` 可选，单位为秒 |
| GET | `/api/v1/tasks/{task_id}/events` | 带时间戳的事件及描述 |
| GET | `/api/v1/tasks/{task_id}/preview/status` | 兼容预览生成状态 |
| GET | `/api/v1/tasks/{task_id}/preview` | 返回 MP4 预览流；未就绪返回 409 |
| WebSocket | `/ws/task/{task_id}` | 任务进度、事件及完成或失败通知 |

图片检测的 `conf` 默认 0.25，范围 0.05～0.9；`iou` 默认 0.55，范围 0.3～0.95。检测框采用归一化中心坐标 `cx/cy/w/h`，前端按实际画布尺寸换算。`video_name` 去除首尾空白后最多保留 120 个字符，空值使用上传文件名。队名和比分字段是输入备注，不是模型识别结果。

### 常见错误

| 状态码 | 场景 |
|---|---|
| 400 | 无效参数、空文件、格式不支持、图片损坏、文件超限或文本不符合要求 |
| 404 | 任务或资源不存在 |
| 409 | 任务处理中禁止删除，或预览尚未生成 |
| 500 | 模型未就绪、推理失败或其他服务器错误 |
| 503 | Celery 模式无法连接消息服务或投递任务 |

批量图片任务当前保存在 API 进程内存中，重启后不会保留。视频任务使用 SQLite 与本地文件保存。

## 7. 单独启动和开发

日常使用一键启动即可。只有需要查看实时日志或调试某个服务时，才分别启动；开始前先关闭已经运行的一键服务。

下面每组命令都从项目根目录开始，在各自的 PowerShell 窗口执行。

**后端 API：**

```powershell
Set-Location .\backend
$env:TASK_BACKEND = 'worker'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**视频 Worker：**

```powershell
Set-Location .\backend
$env:TASK_BACKEND = 'worker'
.\.venv\Scripts\python.exe -m worker.main
```

**前端：**

```powershell
Set-Location .\frontend
pnpm dev --host 127.0.0.1 --port 5173 --strictPort
```

修改模型文件或后端环境配置后，需重启相关服务。

### 前端构建

在 `frontend/` 中运行：

```powershell
pnpm build
```

构建输出在 `frontend/dist/`。Vite 开发代理不会随构建产物一起部署；如需单独托管静态页面，应配置同源的 `/api` 和 `/ws` 转发，并保持后端 API、视频处理服务运行。

## 8. 配置项

在 `backend/.env` 中保存需要覆盖的配置，随后重启 API 和 Worker。未配置时使用默认值；API 与 Worker 应使用同一组数据库、任务目录和调度配置。

| 环境变量 | 默认值或用途 |
|---|---|
| `TASK_BACKEND` | `worker`；可选 `celery` |
| `BASKETBALL_FRAME_STEP` | `2`；设为 `1` 表示逐帧推理 |
| `BASKETBALL_DEVICE` | `auto`；可设为 `cpu` 固定使用 CPU |
| `BASKETBALL_IMAGE_SIZE` | `640`，视频推理输入尺寸 |
| `BASKETBALL_MAX_UPLOAD_BYTES` | `5368709120`，视频上传上限 5 GiB |
| `BASKETBALL_MAX_IMAGE_UPLOAD_BYTES` | `10485760`，图片上传上限 10 MiB |
| `BASKETBALL_MAX_BATCH_IMAGES` | `20` |
| `BASKETBALL_WORKER_POLL_SECONDS` | `1`，独立 Worker 轮询间隔，单位为秒 |
| `BASKETBALL_MODEL_PATH` | 视频模型路径，默认 `backend/weights/best.pt` |
| `BASKETBALL_IMAGE_MODEL_PATH` | 图片模型路径，默认 `backend/weights/a2_int8_val346.onnx` |
| `BASKETBALL_TEXT_MODEL_PATH` | 文本模型路径，默认 `backend/app/ml/text_action_clf.joblib` |
| `BASKETBALL_TEXT_META_PATH` | 文本元数据路径，默认 `backend/app/ml/text_clf_meta.json` |
| `BASKETBALL_DB_PATH` | 默认项目内 `backend/tasks.db` |
| `BASKETBALL_RUNS_DIR` | 默认项目内 `backend/runs/` |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` |

需要自定义文件位置时，建议填写绝对路径。抽帧间隔越大，通常推理工作量越少，但也会减少可用于事件分析的时间采样点。无法读取视频总帧数时，Worker 会逐帧分析。

## 9. 可选 Celery + Redis 模式

默认模式不需要 Redis。本节用于需要验证队列调度的场景；切换前停止 API、独立 Worker 和前端。

### 9.1 安装并准备消息服务

从项目根目录执行：

```powershell
.\backend\.venv\Scripts\python.exe -m pip install -r .\backend\requirements-celery.txt
```

准备可访问的 Redis。若已安装并启动 Docker，可使用：

```powershell
docker run --rm -p 127.0.0.1:6379:6379 redis:7-alpine
```

也可使用已有 Redis，按实际地址设置 `CELERY_BROKER_URL`。

### 9.2 启动 API 与 Celery

在两个新的 PowerShell 窗口中，分别从项目根目录执行。

**窗口一，API：**

```powershell
Set-Location .\backend
$env:TASK_BACKEND = 'celery'
$env:CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**窗口二，Celery：**

```powershell
Set-Location .\backend
$env:TASK_BACKEND = 'celery'
$env:CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
.\.venv\Scripts\celery.exe -A worker.celery_app:celery_app worker --pool=solo --concurrency=1 --loglevel=INFO
```

再按第 7 节单独启动前端。此模式不要同时运行 `worker.main` 或一键启动脚本。任务状态和结果仍保存在相同的 SQLite 数据库与任务目录中，只替换任务调度方式。

Windows 下的 `solo` 工作池已完成本地单任务验证；该记录不包含多机并发或故障恢复。Redis 不可用时，上传接口返回 503，并清理未成功投递的任务记录。

恢复默认模式时，停止以上进程，并将 `backend/.env` 或当前环境中的 `TASK_BACKEND` 恢复为 `worker`，再使用一键启动。

## 10. 检查与测试

从项目根目录开始：

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
pnpm test:unit
pnpm build
pnpm exec playwright install
pnpm test:e2e
```

- 后端测试检查坐标处理和演示 API 的成功、错误路径，部分测试使用替身模型。
- 前端单元测试检查坐标转换；构建命令同时执行 TypeScript 检查。
- 浏览器测试覆盖响应式布局、最近任务导航及上传分析交互。配置中的 Chromium 项目通过本机 Microsoft Edge 运行，Firefox 和 WebKit 使用 Playwright 浏览器。
- 界面自动化测试使用模拟 API/WebSocket 响应，不能代替真实模型推理验证；WebKit 测试也不等同于 macOS Safari 应用实测。
- 真实联调可通过页面上传实际样例，检查进度、检测框、事件定位、手动继续播放和历史回放，并另行保存记录。

测试命令供复现使用，具体通过项和耗时以项目保存的验收记录为准。

## 11. 常见问题

| 问题 | 处理方法 |
|---|---|
| 找不到 pnpm | 先确认 Node.js 与 pnpm 已安装并加入 PATH，再重新打开终端。仅打开网页不能代替安装依赖。 |
| PowerShell 阻止执行激活或 pnpm 脚本 | 后端使用本文的虚拟环境 Python 完整路径，无需激活；若安装目录提供 `pnpm.cmd`，可用它执行对应 pnpm 命令。 |
| 提示忽略 core-js 构建脚本 | 项目的 `frontend/pnpm-workspace.yaml` 已声明该依赖的构建许可，确认配置文件随项目一起保留后重新安装依赖。 |
| 页面打不开或端口被占用 | 先停止已有服务，再启动；手动启动的进程需在原终端停止。查看 `.runtime/logs/` 中的错误信息。 |
| 删除任务返回 Method Not Allowed | 检查是否仍运行不含 DELETE 路由的旧后端；停止该进程后重新启动配套后端。 |
| 页面提示模型未加载 | 核对第 2.4 节的文件路径、模型与元数据，查看健康接口及 API 日志，修复后重启。 |
| 任务一直等待 | 确认 Worker 正常运行；Celery 模式还需确认 Redis、队列配置和消费者正常。 |
| 已有检测结果但视频黑屏 | 可能是本地视频编码不受浏览器支持；等待兼容预览完成后，从历史任务重新打开，或上传 H.264/AAC 编码的 MP4。 |
| 有 GPU 仍使用 CPU | 检查当前虚拟环境中的 PyTorch 和 CUDA 是否可用；CPU 可以继续完成分析，修改显卡运行环境后需重新验证性能。 |
| 点击事件后视频不继续播放 | 这是预期交互：定位后保持暂停，点击播放器播放键继续。 |
| 清除当前任务后历史记录仍在 | 清除按钮只重置当前页面；需要删除记录时在最近任务列表操作。 |
| 图文页显示“投篮”，图片却不是投篮 | 该类别来自文字分类；图像侧只检测球员，图文结果不证明动作一致。 |
