# 后端说明

这是实验四当前集成版后端，包含视频任务 API 与 Worker，以及图像检测、解说文本分类和图文匹配三个演示 API。

首次安装请按上级目录 README.md 执行；后端依赖分别列在 requirements.txt 和 requirements-dev.txt。

单独调试时，在 backend 目录运行：

    .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

然后在另一个终端运行：

    .\.venv\Scripts\python.exe -m worker.main

默认 TASK_BACKEND=worker，使用项目自带的本地 Worker，不需要 Redis。API 参数和响应示例见 http://127.0.0.1:8000/docs。
