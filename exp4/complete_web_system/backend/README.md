# 后端说明

这是实验四当前集成版后端，包含视频任务 API 与 Worker，以及图像检测、解说文本分类和图文匹配三个演示 API。

首次安装请按上级目录 README.md 执行；后端依赖分别列在 requirements.txt 和 requirements-dev.txt。

单独调试时，在 backend 目录运行：

    .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

然后在另一个终端运行：

    .\.venv\Scripts\python.exe -m worker.main

默认 TASK_BACKEND=worker，使用项目自带的本地 Worker，不需要 Redis。API 参数和响应示例见 http://127.0.0.1:8000/docs。

## 第三版对接

`POST /api/v1/tasks` 支持可选字段 `video_name`（去除首尾空白、最多 120 字，空值使用上传文件名）。
`DELETE /api/v1/tasks/{task_id}` 删除已完成或失败的历史任务；处理中的任务返回 409。
前端等待界面读取任务进度，配合 `/ws/task/{task_id}` 和任务查询接口更新。

## 可选 Celery + Redis 模式

先安装 `requirements-celery.txt`，并准备可访问的 Redis，例如已有 Docker 时运行 `docker run --rm -p 6379:6379 redis:7-alpine`。未安装 Docker 的电脑也可使用其他机器提供的 Redis。

停止默认 Worker，然后分别在 API 和 Celery 的终端设置相同配置：

```powershell
$env:TASK_BACKEND = "celery"
$env:CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
```

API：`.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`

Celery：`.\.venv\Scripts\celery.exe -A worker.celery_app:celery_app worker --pool=solo --concurrency=1 --loglevel=INFO`

单独运行前端 `pnpm dev`。此模式不要同时运行 `worker.main` 或一键启动脚本；所有进程使用同一组后端配置。Windows 的 solo 模式已验证一个真实 CPU 视频任务，多机并发和故障恢复不在该测试范围内。
