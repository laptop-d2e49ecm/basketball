# 任务：视频解说 LLM 化 + 聊天页解说模式（产品主线收官）

> **一句话目标**：把"上传视频 → AI 生成解说词"这最后一环接通。目前视频页解说还是模板句（"画面中检测到约 6 名球员"），要换成大模型以解说员口吻生成的解说词。
> 背景：聊天 Agent（/agent 页）已按任务书完成，但产品主线"视频→解说"缺最后一块拼图——`worker/commentary/` 的插拔点当初就是为此预留的。
> 前置：git pull master 最新；后端 `.env` 配好 key（官方直连延迟 ~2s，够用）。
> 预计总工作量：**约 2 小时**（任务一 1.5h + 任务二 0.5h）。

---

## 任务一：视频解说换 LLM（核心）

### 现状（先读这三个文件，共 ~60 行）

| 文件 | 内容 |
|---|---|
| `exp4/complete_web_system/backend/worker/commentary/base.py` | `CommentaryService` 抽象接口：`generate(event: dict) -> str` |
| `exp4/complete_web_system/backend/worker/commentary/stub.py` | 现在的模板实现（要保留，作为回退） |
| `exp4/complete_web_system/backend/worker/video_service.py` | 找到实例化 `StubCommentaryService()` 的位置，改成按配置切换 |

事件 dict 的实际字段（来自 `event_service.py`）：`t_ms`（毫秒）、`type`（`player_count` / `player_cluster` / `group_direction_change`）、`player_count`、`track_ids`，个别带 `text`。

### 要做的

1. 新建 `worker/commentary/llm.py`：`LLMCommentaryService(CommentaryService)`
   - 模型客户端**复用现成的**：`from app.agent.providers import make_chat_model`（worker 从 backend 目录以 `-m worker.main` 运行，app 包可直接导入）；
   - `generate(event)` 实现：中文解说员人设的系统提示 + 事件事实（第几秒、发生了什么）→ 一句解说词。示例提示词结构：
     ```
     你是篮球比赛解说员。根据下面这条画面事件写一句简短的中文直播解说（不超过30字，口语化、有节奏感）。
     只能基于事件里的事实（人数变化/聚集/移动方向），严禁编造投篮、比分、球员姓名等事件里没有的信息。
     事件：第 12.4 秒，画面球员人数从 5 变为 6
     ```
   - **失败必须回退**：LLM 调用异常/超时（设 10s）时，调用 `StubCommentaryService().generate(event)` 返回模板句，**绝不让 Worker 崩**；
   - 模型实例进程内复用（不要每个事件新建客户端）。
2. 开关：`.env` 加 `BASKETBALL_COMMENTARY=stub|llm`（**默认 stub**，没配 key 的机器照常跑）；`video_service.py` 按值选择实现；`.env.example` 与 `app/core/config.py` 同步补一行说明。
3. 可选加分（时间富余再做）：从 `app/agent/tools.py` 的 `_commentary_index()` 检索 1 条真人解说作风格示例拼进提示词。注意 worker 是同步循环，每个事件的 LLM 调用控制在一次以内。

### 注意事项

- 演示视频事件数很少（36s 的 demo_video 约 1-3 个事件），LLM 延迟可接受；不要并发轰炸；
- 解说"能力边界"纪律不变（实验4 就有）：只有人数/聚集/方向的事实，文案别出现模型不存在的信息；
- 在改完的 `.env` 切到 `llm` 后**重启 worker 进程**才生效。

### 验收标准（截图进报告）

- [ ] `BASKETBALL_COMMENTARY=llm` 下提交 `samples/demo_video.mp4`，`GET /api/v1/tasks/{id}/events` 返回的 `text` 是 LLM 生成的解说词（非模板句）；
- [ ] 视频工作台回放页右侧解说面板显示 AI 解说 → **截图**（这就是旗舰演示素材：上传视频→画框→AI 解说）；
- [ ] 故意把 key 改错重启 → 任务仍能完成（回退模板句），Worker 不崩 → 截图或日志佐证；
- [ ] 默认（不配置）仍是 stub，原有测试全绿（`pytest -q`）。

## 任务二：聊天页解说模式（10 分钟提示词改动）

`exp4/complete_web_system/backend/app/agent/graph.py` 的 SYSTEM_PROMPT 第 5 条扩一句：

> 用户给出视频任务编号并问"发生了什么/有哪些事件/给这个视频配解说" → 调用 query_video_events 拿到事件后，**以解说员口吻逐事件播报**（"第X秒……"），而不是只列清单；闲聊与概念问题规则不变。

验收：
- [ ] `/agent` 页输入一个已完成任务的编号 + "给这个视频配解说" → 输出逐事件解说词（截图）；
- [ ] 重跑 `exp5/eval/tool_accuracy.py` 仍 10/10（确认提示词改动无回归）。

## 完成后

1. git 提交推送（提交信息写明"视频解说 LLM 化（旗舰演示闭环）"）；
2. **报告补一节**：第七章加"7.x 视频解说生成"——措辞用现成的非配对方案说明（事实来自视觉模型/事件表、风格来自真人语料与 LLM、两数据源非同场次故不做逐句对齐），配任务一的截图；
3. 提醒：交付 zip 是快照——若此任务在打包后完成，**报告补图后需重新导出 PDF 并重打包**（或按老师要求补交增量）；另外交付版封面的成员分工表目前还是空的，一并填掉。

## 相关文件速查

- 改动点：`worker/commentary/llm.py`（新建）、`worker/video_service.py`（切换）、`app/core/config.py` + `.env.example`（开关）、`app/agent/graph.py`（提示词）
- 复用：`app/agent/providers.py`（模型客户端）、`app/agent/tools.py::_commentary_index`（语料索引，可选）
- 验证素材：`samples/demo_video.mp4`（36s 正式）/ `demo_video_short.mp4`（12s 快验）
