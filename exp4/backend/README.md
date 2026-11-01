# 实验 4 本侧后端（检测 / 文本分类 / 图文匹配 三 API）

集成实验 3 优化模型 `a2_int8_val346.onnx`（INT8，3.6MB，test mAP50=0.420）与
实验 1 语料训练的解说文本动作分类器；统一信封 `{code,result,msg}`，错误码 400/404/500。

## 快速启动

```bash
# 依赖（复用仓库根 .venv 亦可：pip install -r requirements.txt）
python -m pip install -r requirements.txt

# 启动（自动加载 weights/ 与 app/ml/ 下模型，文档见 http://127.0.0.1:8000/docs）
python -m uvicorn app.main:app --port 8000
```

如需重训文本分类器（语料来自实验 1 清洗后解说，约 40 秒）：

```bash
python train_text_clf.py --data ../../data/processed/texts/livetext/commentary.jsonl
```

## API 一览（详细参数/示例见 /docs 与 postman_collection.json）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 服务与模型加载状态 |
| GET | `/api/v1/meta/model` | 模型指标（实验 2/3 实测口径） |
| POST | `/api/v1/detect` | 单张图像检测：归一化框+人数+dropped_boxes+耗时 |
| POST | `/api/v1/detect/batch` | 批量异步（BackgroundTasks，返回 task_id） |
| GET | `/api/v1/batch/{task_id}` | 批量任务进度/结果 |
| POST | `/api/v1/text/classify` | 解说文本动作分类（10 类，域外判定"非篮球赛事文本"） |
| POST | `/api/v1/match` | 图文匹配工作流（检测→文本→一致性，依赖注入串联） |

## 测试与实测

```bash
python -m pytest tests/ -q     # 14 项：坐标往返/信封/异常路径/三 API/批量流转
python bench.py                # 需先起服务；产出 ../bench_results.json
```

2026-11-01 实测（Ryzen 7 6800H CPU，同机 HTTP 往返）：检测 e2e 均值 132.8ms / P95 137.1ms，
文本 7.9ms，图文匹配 139.0ms —— 任务书合格线 2000ms。

## 目录

```
app/
├── main.py            # FastAPI 入口（队友合并时：include_routers + lifespan 并入其 main）
├── api/               # detect / text / match / health 路由
├── core/              # config / errors(400/404/500) / schemas(信封契约) / coords(坐标唯一实现)
└── services/          # detector(ONNX) / text_clf / workflow(图文匹配) / batch_store(异步)
weights/               # a2_int8_val346.onnx + best.pt（视频主线 track 用）
app/ml/                # text_action_clf.joblib + text_clf_meta.json
tests/  postman_collection.json  bench.py  train_text_clf.py  preprocess.py(实验1规则复用)
```

## 与视频主线（队友）合并

1. 将本目录 `app/api/*` 路由与 `lifespan` 模型加载并入其 `app/main.py`（路由零改动）；
2. 共享 `app/core/`（errors/schemas/coords/preprocess 均为双方契约件，交接包内同款）；
3. REST 统一 `/api/v1` + 信封；WS `/ws/task/{id}` 归视频主线。
