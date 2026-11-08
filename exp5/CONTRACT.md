# 实验5 Agent 接口契约 v1.0（/api/v1/agent/chat）

> **读者**：前端（队友）按第 2-4 节开发与 mock；测试按第 4、8 节写用例；后端（本侧）按全文实现。
> **原则**：完全延续实验 4 规范——统一信封 `{code, result, msg}`、错误码 400/404/500、`/api/v1` 版本前缀、CORS 放行 `localhost:5173`。任务书要求的新增错误 **404 ToolNotFound** 见第 4 节。
> **变更规则**：先改本文、再改代码；任何一方发现代码与本文不一致，以本文为准并立刻同步。
> 挂载位置：实验 4 后端 `exp4/complete_web_system/backend/`（端口 8000，`/docs` 自动生成接口文档）。

---

## 1. 接口基本信息

| 项 | 值 |
|---|---|
| 方法与路径 | `POST /api/v1/agent/chat` |
| Content-Type | `application/json` |
| 会话机制 | 首轮**不传** `session_id`，后端新建并在响应返回；之后每轮原样带回（断点续聊，SQLite 持久化） |
| 流式 | v1 **不做** SSE 流式，一次请求一次返回；"正在调用 xx 工具"由前端根据响应内 `tool_calls` 过程渲染（见 7.2） |
| 超时 | 前端 Axios 建议 timeout 60s；后端 LLM 超时阈值见第 6 节 |

## 2. 请求体

```json
{
  "session_id": "sess_a1b2c3",   // 可选；首轮省略
  "message": "samples/images/f000005.jpg 这张图里有几个球员？"   // 必填，1~500 字符
}
```

校验规则：`message` 非空、为字符串、≤500 字符，否则 400。

## 3. 响应体（成功 code=0）

统一信封内 `result` 结构：

```jsonc
{
  "code": 0,
  "msg": "ok",
  "result": {
    "session_id": "sess_a1b2c3",          // 前端保存，下轮带回
    "agent": "这张图里检测到 10 名球员，平均置信度 0.87，主要分布在画面中部。",  // 最终中文回复（直接渲染为气泡）
    "tool_calls": [                        // 本轮 Agent 实际调用的工具过程（按发生顺序）
      {
        "tool": "player_detect",           // 工具名，见第 5 节
        "args": { "image_path": "samples/images/f000005.jpg" },  // 原样入参
        "status": "ok",                    // ok | error（error 不导致整轮失败）
        "result_summary": "检出 10 人，平均置信度 0.87",   // 给人看的一行摘要
        "elapsed_ms": 146
      }
    ],
    "elapsed_ms": 2100,                    // 本轮端到端耗时
    "provider": "api"                      // api | ollama，排查用，前端可不展示
  }
}
```

`tool_calls` 可能为空数组（纯闲聊，Agent 未调工具）。

## 4. 错误码表（复用实验 4 全局异常 handler）

| code | 场景 | msg 示例 | 前端动作 |
|---|---|---|---|
| 400 | message 空 / 超长 / 类型错 | 消息不能为空 | 输入框校验 + 提示 |
| 404 | **ToolNotFound**（Agent 选择了不存在的工具）/ session_id 无效 | 工具不存在，请换个说法描述需求 | 弹提示，保留输入 |
| 500 | LLM 调用失败（已重试 3 次） | AI 服务暂时不可用，请稍后重试 | 显示"请重试"按钮重发上一条 |
| 504 | LLM 超时（阈值见第 6 节） | AI 响应超时，请重试 | 同上 |

信封格式与实验 4 完全一致：`{ "code": 400, "result": null, "msg": "..." }`。前端 Axios 拦截器（实验 4 已有）读 code/msg 弹友好提示，无需逐接口处理。

## 5. 工具清单（`tool_calls[].tool` 的合法取值）

前端只展示"工具中文名 + status + 耗时"，不用理解入参细节。

| tool 名 | 中文名（前端展示用） | 入参 | result_summary 内容 | 对应实验 4 |
|---|---|---|---|---|
| `player_detect` | 球员检测 | `{image_path}` 服务端相对路径，演示用 `exp4/complete_web_system/samples/images/` 下 **test 划分**图 | 检出人数、平均置信度 | `/api/v1/detect` 同一实现 |
| `commentary_classify` | 解说文本分类 | `{text}` | 动作类别 + 置信度 | `/api/v1/text/classify` 同一实现 |
| `image_text_match` | 图文匹配 | `{image_path, text}` | 一致性结论 + 两侧证据 | `/api/v1/match` 同一实现 |
| `query_video_events` | 视频事件查询 | `{task_id}` | 事件数 + 最近事件类型 | `/api/v1/tasks/{id}/events` |
| `retrieve_commentary` | 解说语料检索 | `{query, top_k?}` 默认 3 | 真人解说例句 top3 | BM25 检索 livetext `split_train` |

> 图像路径怎么来：对齐任务书"输入图像路径"的场景，用户**直接在消息里打路径**（如 `samples/images/f000005.jpg 这图有几个人`），Agent 自行提取后调用工具；后端工具内做路径白名单校验（只允许 samples/ 与 runs/ 下），防任意路径读取。

## 6. 超时、重试与日志（后端行为，测试用例依据）

- **工具调用**：失败重试 3 次（退避 1s/2s/4s）；仍失败则该条 `status="error"`，Agent 拿错误信息继续组织回复，**整轮不失败**。
- **LLM 调用**：超时阈值 API 30s / Ollama 60s；超时→504。
- **日志**：`logs/agent.jsonl` 逐轮追加 `{ts, session_id, user, tool_calls, elapsed_ms, provider}`，联调排障与报告"延迟表"数据来源。

## 7. 会话存储与前端联调

### 7.1 会话格式（SQLite 表 `agent_sessions`，与实验 4 tasks.db 同库）

`history` 字段存 JSON 数组，字段命名对齐任务书重点（user / agent / tool_calls）：

```json
[
  { "role": "user",   "content": "samples/images/f000005.jpg 有几个人？" },
  { "role": "agent",  "content": "这张图里检测到 10 名球员…", "tool_calls": [ { "tool": "player_detect", "...": "同第 3 节" } ] }
]
```

断点续聊：带同一 `session_id` 再来即续上文（多轮场景 3 的依据）。

### 7.2 前端开发指引（队友）

- 路由 `/agent`，NavBar 增"AI 解说"项（AntD Vue）；
- **联调前**直接用第 3 节 JSON mock（Axios 适配器或本地 json），不必等后端；
- 气泡区渲染 `agent` 文本；`tool_calls` 渲染为可折叠过程条，如：`🔧 球员检测 · 成功 · 146ms`；等待期间显示"AI 正在思考…"；
- 错误按第 4 节动作处理；移动端：气泡 `max-width` + `word-break`，复用实验 4 响应式断点。

## 8. 测试用例锚点（测试成员直接抄）

| 用例 | 请求 | 期望 |
|---|---|---|
| 场景1 图像 | message 含 test 图路径 + "有几个球员" | code=0，tool_calls 含 `player_detect`，agent 报人数 |
| 场景2 文本 | message 为解说样例（`samples/texts/解说样例.jsonl` 任取） | code=0，含 `commentary_classify`，类别正确 |
| 场景3 多轮 | 先"怎么判断图里有没有球员？"，再（同 session_id）给路径 | 第二轮正确调用工具（验证上下文） |
| 空消息 | `{"message": ""}` | code=400 |
| 坏 session | `{"session_id": "sess_不存在", "message": "hi"}` | code=404 |
| 超时 | mock 工具/LLM 延迟 | code=504，前端显示"请重试" |

## 9. curl 示例

```bash
# 首轮
curl -X POST http://127.0.0.1:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "samples/images/f000005.jpg 这张图里有几个球员？"}'

# 多轮（续聊）
curl -X POST http://127.0.0.1:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess_a1b2c3", "message": "再看看这张 samples/images/f000025.jpg"}'
```

Postman：在实验 4 `postman_collection.json` 基础上新增 "Agent" 目录挂两个用例（首轮/续聊）。

## 10. 环境变量（后端 `.env`，从 `exp5/.env.example` 复制，**勿提交 git**）

```ini
EXP5_LLM_PROVIDER=api                      # api | ollama（本地兜底）
EXP5_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/   # 智谱；DeepSeek: https://api.deepseek.com/v1 ；阿里百炼: https://dashscope.aliyuncs.com/compatible-mode/v1 ；Ollama: http://127.0.0.1:11434/v1
EXP5_LLM_API_KEY=你申请的key
EXP5_LLM_MODEL=GLM-5.3-Flash               # 准确模型 id 以各平台控制台"模型列表"为准（任务书示例：GLM-5/GLM-5.3、DeepSeek-V4-Flash、Qwen3.5）
```

三家国内平台均为 **OpenAI 兼容端点**，代码统一走 `langchain-openai` 的 `ChatOpenAI(base_url, api_key, model)`，换厂商只改这三个变量，不改代码。

## 11. 版本记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v1.0 | 2026-11-08 | 定稿：路径/信封/错误码/工具清单/会话格式/超时重试 |
