# 篮球赛事视频分析完整交接包

本目录为当前第三版集成程序，包含前端、配套后端、三个模型、样例和一键启动脚本。仓库默认分支 `master` 使用此版本，固定版本标签为 `frontend-v3.0.0`。

## 从这里运行

从仓库根目录进入 `exp4/complete_web_system/`，或下载旁边的 `complete_web_system.zip` 后解压。`exp4/frontend/` 和 `exp4/backend/` 保留早期模块源码，当前完整应用请运行本目录。

首次安装需要 Python 3.11 或 3.12、Node.js 20.19+（或 22.12+）和 pnpm。在本目录打开 PowerShell：

```powershell
Set-Location .\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location ..\frontend
pnpm install
```

安装完成后双击 **start_project_v3.bat**。本目录只保留这一个启动入口，以及用于关闭服务的 **stop_project.bat**；两个 BAT 已内置 PowerShell 逻辑，不依赖单独的 PS1 文件。脚本在后台启动 API、Worker 和前端，并打开 `http://127.0.0.1:5173/video-v3`；停止服务使用 `stop_project.bat`。API 文档在 `http://127.0.0.1:8000/docs`。

默认独立 Worker 模式无需 Redis。视频推理在可用时选择 CUDA，否则使用 CPU；ONNX 图片检测使用 CPU。切换代码版本前先停止旧服务，避免旧 API 占用 8000 端口。

## 第三版功能

- 默认首页与 `/video` 跳转到 `/video-v3` 视频分析工作台。
- 选择 MP4 后出现“正在分析中，请稍等”，进度条由 WebSocket / REST 的任务进度更新，结果载入后关闭等待界面；上传或分析失败会显示原因。
- 视频画面占较大宽度，关键事件在右侧；人数变化图跨两列。点击事件定位视频并保持暂停。
- 比赛画面的“历史任务”按钮可打开最近任务；检测、文本和图文页面也可通过导航返回最近任务。
- “清除当前任务”清空当前预览、事件、检测框和图表，随后可重新上传。此操作保留历史记录，也不会取消已提交到后端的分析任务。
- 最近任务支持打开历史分析及删除已完成、失败的任务；处理中的任务禁止删除。
- `/detect` 球员图片检测，`/text` 解说文本分类，`/match` 图片与文本的篮球相关性演示；结果图片可点击放大。
- 上传时可填写视频名称，由后端保存；视频默认最大 5 GiB，图片最大 10 MB。

视频描述来自人数变化、聚集和群体移动等启发式事件，不识别投篮、进球、姓名或比分。图文模块汇总“图片检出球员”和“文本属于篮球内容”两类证据，不验证图片动作与解说动作一致。

新上传的视频直接使用浏览器本地预览，其播放能力取决于编码；历史任务通过后端兼容预览接口播放。模型推理始终读取原视频。

## 代码和配套文件

- `frontend/src/`：Vue 路由、公共导航及图片/文本/图文页面。
- `frontend/src/views/VideoV3View.vue`：工作台入口，加载 `frontend/public/前端第三版.html`。**public 里的文件是实际运行页面**。
- `backend/`：FastAPI、任务存储、视频 Worker、模型及演示 API；后端支持任务名称和删除，更新时请配套使用。
- `samples/`：图片、文本和视频样例；`demo_video.mp4` 为 36.04 秒基线，`demo_video_short.mp4` 用于快速检查。
- `backend/postman_collection.json`：接口请求集合。
- `tests/VERIFIED_TESTS.md`：本次验证记录和复现说明。
- `reports/`：视频基线及真实 API/异步任务/浏览器显示延迟记录。
- [Edge 真实视频完整流程联调](reports/video-integration-20261106/README.md)：13 项检查通过，含原始 JSON、截图、服务日志和执行追踪；独立于 60 项模拟接口界面测试。

## 检查命令

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
pnpm test:unit
pnpm build
pnpm exec playwright install
pnpm test:e2e
```

浏览器测试使用固定 API 响应，默认 Chromium 项目通过本机 Microsoft Edge 运行；Firefox / WebKit 使用 Playwright 浏览器。真实模型测试与界面交互测试分开记录。

可选 Celery + Redis 模式的配置见 [后端说明](backend/README.md)。一键脚本启动的是默认独立 Worker。

## 使用之前的版本

第一版标签 `frontend-v1.0.0`、第二版标签 `frontend-v2.0.0` 保持原提交，可从 GitHub 的 Tags 中查看、下载。建议解压到不同目录后安装依赖、启动；切换运行版本前先停止正在运行的服务。

```powershell
git archive --format=zip --output=frontend-v1.zip frontend-v1.0.0:exp4/complete_web_system
git archive --format=zip --output=frontend-v2.zip frontend-v2.0.0:exp4/complete_web_system
```
