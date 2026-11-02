# 篮球赛事视频分析完整交接包

本目录收录当前已集成的前后端程序、模型、样例、运行脚本和测试记录，供组员直接下载、运行和继续开发。

## 包含内容

- backend/：FastAPI 服务、视频任务 Worker、图像检测/文本分类/图文匹配 API，以及后端测试。
- frontend/：Vue 前端、单元测试和响应式页面验收用例。
- backend/weights/ 与 backend/app/ml/：视频球员检测模型、ONNX 图像检测模型和文本分类模型。
- samples/：可直接上传的视频、图片及解说文本样例。
- backend/postman_collection.json：三个演示 API 的 Postman 请求集合。
- start_project.bat / stop_project.bat：一键启动和停止本地 API、Worker、前端。
- tests/VERIFIED_TESTS.md：已通过的构建和测试记录。
- docs/：实验四计划与架构设计参考。

## 首次安装（Windows）

要求：Python 3.11 或 3.12、Node.js 20.19+（或 22.12+）和 pnpm。

在本目录打开 PowerShell，依次运行以下命令：

    Set-Location .\backend
    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    Set-Location ..\frontend
    pnpm install

如果电脑使用的 Python 命令不是 py -3.12，可将它换成已安装的 Python 3.11 或 3.12 命令。

## 启动和停止

完成首次安装后，在本目录双击 start_project.bat，或在 PowerShell 运行：

    .\start_project.ps1

脚本会在后台启动 API、视频 Worker 和前端，并打开浏览器。页面地址为 http://127.0.0.1:5173，后端接口文档为 http://127.0.0.1:8000/docs。需要停止时运行 stop_project.bat。

默认使用独立 Worker，不需要先安装 Redis。视频模型会自动选择 CUDA GPU；没有可用 CUDA 时回退到 CPU。ONNX 图像演示接口使用 CPU Provider。

## 主要功能

- /video：上传篮球视频，查看分析进度、检测结果和带检测框的视频预览。
- /detect：球员图片检测，支持批量图片任务。
- /text：篮球解说文本分类。
- /match：单张图片与一段解说文本匹配。
- REST API 与任务 WebSocket：接口说明可从 /docs 查看。

单个视频默认最大 5 GiB；抽帧间隔由 BASKETBALL_FRAME_STEP 控制，默认每 2 帧处理 1 帧。视频时长和分辨率会影响总处理时间。

## 本地验证命令

    Set-Location .\backend
    .\.venv\Scripts\python.exe -m pytest -q

    Set-Location ..\frontend
    pnpm test:unit
    pnpm build
    pnpm test:e2e

可按需复制 backend/.env.example 为 backend/.env 调整 Worker、抽帧间隔、上传大小或设备选择。默认值已经可以直接启动。
