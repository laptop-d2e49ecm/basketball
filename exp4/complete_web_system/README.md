# 篮球赛事视频分析完整交接包

本目录为最终版集成程序，包含前端、配套后端、三个模型、样例和一键启动脚本。历史版本标签 `frontend-v1.0.0`～`v3.0.0` 可从 GitHub Tags 查看。

## 从这里运行

推荐从仓库根目录双击 **一键启动.bat**（拉起 API、Worker 与前端并打开 `http://127.0.0.1:5173/courtvision.html`）；本目录的 `start_project_v3.bat` / `stop_project.bat` 为等效的目录内入口。API 文档在 `http://127.0.0.1:8000/docs`。

首次安装需要 Python 3.11 或 3.12、Node.js 20.19+（或 22.12+）和 pnpm。可复用仓库根目录的 `.venv`，或在本目录自建：

```powershell
Set-Location .\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location ..\frontend
pnpm install
```

默认独立 Worker 模式无需 Redis。视频推理在可用时选择 CUDA，否则使用 CPU；ONNX 图片检测与动作识别使用 CPU。切换代码版本前先停止旧服务，避免旧 API 占用 8000 端口。

## 当前功能

- 上传 MP4（可填视频名称、主客队与比分）后，后台按“检测 → 动作识别 → 解说生成”三阶段处理：A2′ ONNX INT8 检测球员并跟踪，MC3-18 识别 13 类动作，大模型批量生成逐事件解说（批量 5 条/次，配额消耗降为 1/5，403/429 熔断 10 分钟）。
- 整场 AI 解说按 20 个事件一段生成，防幻觉禁词按“硬禁／比分类／画面证据类”三层分级；可在线播放神经语音（edge-tts 云健音色，高潮句 +35% 语速 +25Hz 音调），并导出解说稿全文与 MP3。
- 视频 workbench 为深色控制台整页 `frontend/public/courtvision.html`（经 `/video-v3` 嵌入）：画面帧条、事件解说带、人数曲线、整场解说面板与右侧 AI 对话。
- `POST /api/v1/agent/chat`（LangChain Agent，5 个工具：球员检测、解说分类、真人解说检索、图文匹配、任务事件分页查询；SQLite 会话支持断点续聊）。需在 `backend/.env` 配置大模型 key（模板见仓库 `exp5/.env.example`），未配置时其余功能不受影响。
- “历史任务”与“最近任务”支持打开历史分析及删除已完成、失败的任务；处理中的任务禁止删除。“清除当前任务”清空当前预览后可重新上传。
- 上传视频默认最大 5 GiB，图片最大 10 MB。

视频事件由 13 类动作识别与人数变化、聚集等启发式事件共同生成；比分与队名来自用户上传时填写（不做记分牌识别），解说不出现事实无法支撑的断言。

新上传的视频直接使用浏览器本地预览，其播放能力取决于编码；历史任务通过后端兼容预览接口播放。模型推理始终读取原视频。

## 代码和配套文件

- `frontend/src/`：Vue 外壳（导航/路由）与 AI 对话页 AgentChatView。
- `frontend/src/views/VideoV3View.vue`：工作台入口，加载 `frontend/public/courtvision.html`。**public 里的文件是实际运行页面**。
- `backend/`：FastAPI、任务存储、视频 Worker（检测/动作/事件/解说/整场解说/语音）与演示 API。
- `samples/`：图片、文本和视频样例；`demo_video.mp4` 为 36.04 秒基线，`demo_video_short.mp4` 用于快速检查。
- `backend/postman_collection.json`：接口请求集合。
- `tests/VERIFIED_TESTS.md`：本次验证记录和复现说明。
- `reports/`：视频基线及真实 API/异步任务/浏览器显示延迟记录；其中 [Edge 真实视频完整流程联调](reports/video-integration-20261106/README.md) 为 13 项检查的历史存档。

## 检查命令

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
pnpm build
pnpm exec playwright install
pnpm test:e2e
```

浏览器测试（13 项）使用固定 API 响应，默认 Chromium 项目通过本机 Microsoft Edge 运行；Firefox / WebKit 使用 Playwright 浏览器。真实模型测试与界面交互测试分开记录。

可选 Celery + Redis 模式的配置见 [后端说明](backend/README.md) 与 [实验 4 说明](../README.md) 第 9 节。一键脚本启动的是默认独立 Worker。

## 使用之前的版本

第一版标签 `frontend-v1.0.0`、第二版标签 `frontend-v2.0.0` 保持原提交，可从 GitHub 的 Tags 中查看、下载。建议解压到不同目录后安装依赖、启动；切换运行版本前先停止正在运行的服务。

```powershell
git archive --format=zip --output=frontend-v1.zip frontend-v1.0.0:exp4/complete_web_system
git archive --format=zip --output=frontend-v2.zip frontend-v2.0.0:exp4/complete_web_system
```
