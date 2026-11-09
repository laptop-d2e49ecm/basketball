# 实验 5 团队执行计划：大模型 Agent——AI 篮球解说员（产品收官）

> 依据：`实验5任务书.pdf`（6 页全文核对）+ 本仓库实验 1-4 实际产出 + `docs/TEAM_PLAN.md` 实验五主线（RAG + LoRA + 工具编排）。
> 总计划仍是 `docs/TEAM_PLAN.md`；本文是实验 5 的**专项执行计划**，照着做即可。
> 任务书是通用模板（技术博客分类 / 猫图像 / React），本项目为 **AI 篮球赛事解说员**，下表完成全部硬性要求的映射，执行时不再犹豫。

---

## 一、任务书要求 → 本项目映射（执行总纲）

| 任务书原文（通用模板） | 本项目对应 | 落点 |
|---|---|---|
| 实验1 文本数据 text_data.json、技术博客主题分类 | 实验1 解说语料 `data/processed/texts/livetext/`（41 场 40,376 条；train 32,377 / test 3,110）、解说**动作/场景分类**（实验4 文本页同款任务） | 5.1.2 微调数据、5.2.1 基线 |
| 实验1 的图像（猫图路径→返回"猫"） | 实验1 **test 划分**球员检测图（`exp4/complete_web_system/samples/images/`，防泄漏纪律） | 5.3.2 场景1 |
| 实验2 LoRA 微调技术 | 实验2 报告已注明"LoRA 留实验5"——本实验**从零定 LoRA 超参**（r/alpha/目标模块），并在报告对比小模型微调（实验2 YOLO 迁移训练）与大模型 QLoRA 差异 | 5.2.2 |
| 实验3 量化方法、4-bit 降延迟/降显存 | ① 微调用 **QLoRA 4-bit + 梯度累积 8 步**（任务书原话）；② 本地推理用 **Ollama Q4_K_M** 量化版 Qwen——报告以此对应"量化前后延迟对比" | 5.2.2 / 5.4.3 |
| 实验4 图像分类 API / 文本分类 API | `/api/v1/detect`（ONNX INT8 球员检测）、`/api/v1/text/classify`（joblib 分类器）、`/api/v1/match`、`/api/v1/tasks`+WS | 5.3.1 工具 |
| 实验4 前端 React 项目、AgentChat.tsx | 我们实验4 用 **Vue3 + AntD Vue**（任务书实验4 允许 "React 19+（或 Vue 3+）"，实验5 延续同一论证）→ 新增 **AgentChatView.vue**，路由 `/agent` | 5.4.2 |
| Agent 服务 localhost:8001 | **主方案挂进实验4 后端 :8000**（`/api/v1/agent/chat` 与 v1 版本一致，复用信封/错误码/CORS/SQLite 断点续聊）；任务书 8001 为"Agent 服务"示意，报告说明合并部署理由 | 5.4.1 |
| Redis+Celery 工具调用队列 | 实验4 已留 `celery_app.py` 双模式；Agent 工具为同步轻调用**不强制入队**，把"并发视频任务经 Celery 分发、Agent 查询走 REST"写入报告双模式说明即可 | 难点2 |

**实验5 的双重目标**：① 完成任务书 Agent 闭环（微调→工具调用→部署交互）；② 落地 TEAM_PLAN 主线"CommentaryService 换 LLM"——实验4 视频 Worker 的 `worker/commentary/stub.py` 桩换成 LLM 版，Agent 成为真正的 AI 解说员。

---

## 二、实验 1-4 资产盘点（全部已就位，直接复用）

| 资产 | 位置 | 实验5 用途 |
|---|---|---|
| 解说语料（40,376 条，8:1:1 分卷） | `data/processed/texts/livetext/split_*.jsonl` | 抽 100 条构造微调指令集；RAG 检索库 |
| 事件表（18 类动作、6,247 行） | `data/processed/multisports/events.csv` | 加分：(事件特征→解说词) 指令对、Agent 事件工具 |
| 球员检测图（test 划分抽样 8 张+GT） | `exp4/complete_web_system/samples/images/` | 场景1 图像工具测试（只用 test！） |
| 解说样例 20 条（test 划分） | `samples/texts/解说样例.jsonl` | 场景2 文本分类测试 |
| `best.pt`(A2′) / `a2v2_int8_val173.onnx` | `exp4/complete_web_system/backend/weights/` | 工具背后的模型。**✅ v2 已更换（2026-11-08）**：A2′ clean190 mAP50 **0.992**、INT8 **0.990**；接口与 Agent 工具封装零改动，冒烟 3/3 + 接口回归 5/5 复测通过（f000005 平均置信度 0.51→0.89） |
| FastAPI 后端（信封/错误码/CORS/SQLite/WS） | `exp4/complete_web_system/backend/` | Agent API 宿主；`app/services/` 为工具实现层 |
| Vue3 前端（四页+NavBar+响应式） | `exp4/complete_web_system/frontend/` | 新增 /agent 页挂进骨架 |
| CommentaryService 抽象 + 桩 | `backend/worker/commentary/{base,stub}.py` | **实验5 预留插拔点**，新增 `llm.py` |
| 一键启动 / 测试矩阵（pytest+vitest+Playwright/Edge） | `start_project_v3.bat`、`tests/VERIFIED_TESTS.md` | 实验5 沿用启动与跨浏览器验证流程 |
| 云训练打包先例 | `exp2_colab_pkg.tar` / `exp3_kaggle_pkg.tar` | 仿制 `exp5/colab_pkg/`（本机无 GPU，QLoRA 上云） |

---

## 三、技术方案（已定死，不再摇摆）

### 3.1 基座模型：双 Provider，API 主力 + 本地兜底

| 线路 | 模型 | 用途 | 理由 |
|---|---|---|---|
| **API 主力** | GLM-5-Flash / DeepSeek-V4-Flash / Qwen（OpenAI 兼容端点，三选一，基线评估后定） | Agent 在线推理 | 本机无 GPU；满足"响应≤5 秒"；`langchain-openai` 的 `ChatOpenAI(base_url=...)` 全兼容 |
| **本地兜底** | Ollama + Qwen3.5 1.7B/4B **Q4_K_M** | 断网/API 故障降级 + "量化前后延迟对比"实验素材 | 任务书量化叙事（4-bit）落点之一 |
| **微调基座** | Qwen3.5-1.7B-Instruct（云端 Colab T4 / Kaggle） | QLoRA 4-bit + SFTTrainer + 梯度累积 8 步 | 任务书点名三件套；T4 16G 显存内可控 |

Provider 切换用环境变量 `EXP5_LLM_PROVIDER=api|ollama`（`exp5/agent/providers.py` 统一构造），API key 走 `.env`（**入 `.gitignore`，见隐私清单**）。

### 3.2 Agent 核心（阶段3 主体）

- **框架**：LangChain ≥1.0，`create_agent`（新版 agent API，基于 langgraph）初始化；系统提示词强制中文解说员人设 + 工具选择规则。
- **工具**（先 3 个保任务书，后 2 个加分，全部注册描述写清输入类型防误选）：

| 工具名 | 封装对象 | 对应任务书 |
|---|---|---|
| `player_detect` | 实验4 检测服务（与 `/api/v1/detect` 同一实现）→ 人数+归一化框 | 场景1 |
| `commentary_classify` | 实验4 文本分类器（与 `/api/v1/text/classify` 同一 joblib）→ 动作类别+置信度 | 场景2 |
| `image_text_match` | `/api/v1/match` 服务函数 → 图文一致性结论 | 加分 |
| `query_video_events` | `GET /api/v1/tasks/{id}/events` → 事件列表 | **主线**：AI 解说员看事件流 |
| `retrieve_commentary` | BM25/TF-IDF 检索 `split_train` 语料（零向量库依赖） | **主线**：RAG 风格参考 |

- **工具实现方式（重要决策）**：默认**同进程复用 `app/services/` 内部函数**（零 HTTP 自调用死锁风险、零额外延迟），工具 docstring 与 REST 契约一一对应，报告表述"Agent 工具=实验4 API 的服务层封装（同一实现）"。若需严格字面"调 REST"，切 httpx 时**必须用 AsyncClient**（async 路由内同步 httpx 自调用 8000 会死锁——写进坑清单）。
- **多轮记忆**：`session_id` → SQLite 会话表，历史按任务书字段 `{user, agent, tool_calls[]}` 存 JSON，支持断点续聊。
- **异常与重试**：工具调用失败重试 3 次（指数退避），日志记录用户查询+工具响应（`logs/agent.jsonl`）；错误码复用 400/404/500，新增 **404 ToolNotFound**。

### 3.3 部署与前端（阶段4 主体）

- **后端**：`app/api/agent.py` 挂 `/api/v1/agent/chat`（POST，入参 `{session_id?, message}`，出参统一信封，`result.agent` 文本 + `result.tool_calls` 过程）；沿用实验4 CORS 白名单 5173。
- **前端**：`AgentChatView.vue`（/agent 路由，NavBar 增"AI 解说"项）：
  - 对话气泡 + **工具调用过程展示**（"正在调用球员检测工具…"，任务书难点3）；
  - 响应文本限长自动换行、Flexbox+媒体查询移动端适配（复用实验4 响应式）；
  - 超时/失败 → "请重试"提示（Axios 拦截器复用实验4）。
- **主线彩蛋（演示加分）**：视频 Worker 的 `CommentaryService` 换 LLM 版（`worker/commentary/llm.py`：事件 dict → LLM 生成中文解说，复用 Agent 同一 provider），视频页解说面板文案升级。演示表述注意：MultiSports 视频本身**没有真人解说**（学术数据集只有动作标注），对比侧展示的是"RAG 检索到的、类似局面下真人怎么说"——是**风格参照**，不是同场配对，报告与演示话术都按这个说。

### 3.4 微调方案（阶段2 主体）

- **数据**：`build_finetune_data.py` 从 `split_train.jsonl` 分层抽 100 条（覆盖主要动作类别），复用实验1 清洗逻辑（去停用词、标点标准化——`code_reuse/preprocess.py` 口径），输出任务书命名的 `agent_finetune_data.json`：

```json
{"instruction": "你是篮球解说助手，判断下面解说的动作场景并按类别标签作答",
 "input": "库里外线出手，三分命中！",
 "output": "投篮得分 / 三分"}
```

  - 构成：**60 条分类**（对齐任务书"基于实验1文本分类任务"+可评估）+ **40 条解说生成**（注意：解说语料与 events.csv 非同批次比赛，**时间对齐不可行**，改用"动作类别语义配对"——input 取 events.csv 真实动作类型合成的局面描述，output 取同类别真人解说原句；只作风格学习不进准确率评估）。
- **训练**：`train_lora.py` = TRL `SFTTrainer` + PEFT LoRA（r=16, alpha=32, dropout=0.05, 目标模块 q/k/v/o）+ `load_in_4bit` + 梯度累积 8 步 + max_len 512；打包 `exp5/colab_pkg/`（仿 exp2 先例）上 Colab T4。
- **评估三方对比表**（报告核心素材，任务书"微调前后准确率"+"小模型 vs 大模型微调差异"一表打尽）：
  10 条 `split_test` 解说 → ① 实验4 joblib 小分类器 ② LLM 零样本 ③ LLM+LoRA 微调，各测动作分类准确率。

---

## 四、四阶段执行清单（课内 6 学时 + 课外并行）

### 阶段1 环境与数据（1 学时）——5.1 模块

1. 后端 venv 装 `langchain langchain-openai peft trl accelerate`（Ollama 另机装，`ollama pull qwen3.5:1.7b-q4_k_m`）；`.env` 配 API key 并入 `.gitignore`。
2. 跑 `build_finetune_data.py` → `agent_finetune_data.json`（100 条，schema 自检：字段齐、无泄漏 test 样本）。
3. 双 provider 冒烟：API 与 Ollama 各问一句"用一句话介绍篮球解说"，确认连通。

**验收**：100 条数据过校验；两 provider 冒烟日志存 `exp5/logs/`。

### 阶段2 选型与微调（1 学时，云端后台跑，本地同时进阶段3——流水线）

1. **零样本基线**：`baseline_zeroshot.py` 用 10 条 test 解说测候选基座零样本分类准确率，定主力 API 模型，数字落表。
2. 打包 `colab_pkg/` 上传 Colab T4 开训 QLoRA（约 1-2h，后台）；本地不等训练结果。
3. （主线加分）`retrieve_commentary` BM25 检索工具先行——零依赖，语料现成。

**验收**：基线表（模型×准确率）；训练 loss 曲线截图；微调后 10 条准确率（训练完成后补测）。

### 阶段3 Agent 框架集成（2 学时）——5.3 模块

1. `exp5/agent/tools.py` 封装 3+2 工具（先 detect/text 两个必做，match/events/RAG 依次加）。
2. `graph.py`：`create_agent` + 中文系统提示词（人设/工具规则/输出约束）。
3. `eval/tool_accuracy.py`：**10 轮任务书场景问句**（图像类问题→应选 player_detect…）统计工具选择准确率，目标 ≥90%；不达标先改工具描述与提示词，仍不达标再加前置意图路由。
4. 多轮测试：先问"如何判断图像里有没有球员"，再给路径——验证上下文理解。

**验收**：单轮/多轮对话记录（`exp5/logs/agent_smoke.md`）；10 轮准确率数字。

### 阶段4 部署与测试（2 学时）——5.4 模块

1. `app/api/agent.py` + 会话表 + 重试/日志，挂进实验4 后端；Postman 集合补 agent 用例。
2. `AgentChatView.vue` 挂 `/agent`；思考过程展示、错误提示、移动端断点检查。
3. `worker/commentary/llm.py` 替换 stub（主线彩蛋，时间不够则砍，不阻塞任务书验收）。
4. **端到端三场景**（任务书原文照测）：① test 图像→Agent 报"检测到 N 名球员"；② test 解说文本→正确动作类别；③ 多轮上下文。截图入报告。
5. **性能与兼容**：文本/图像/多轮平均延迟（API vs 本地 Q4 两口径，目标 ≤5s）；Edge/Firefox/移动端视口逐项点检（复用实验4 矩阵）；异常注入（工具超时→前端"请重试"、后端 jsonl 日志有记录）。

**验收**：三场景 e2e 通过截图；延迟表；跨浏览器点检表；`pytest`/`pnpm test:unit`/`test:e2e` 全绿。

### 课后：报告与打包

- 报告按第六节骨架写，打包 `实验5_完整代码模型与报告.zip`（exp5/ + complete_web_system 增量 + LoRA adapter + 报告）。

---

## 五、分工（字母对应到人后填名字；不足 6 人按序合并：微调→数据、测试→前端、主线彩蛋可砍）

| 角色 | 范围 | 关键产出 |
|---|---|---|
| **A 微调线**（数据+训练合并为一人，专用手册见 `exp5/微调线执行手册.md`） | 基线评估、QLoRA 云端训练、三方对比表 | `train_lora.py`、adapter、对比表 |
| **C Agent 后端**（关键路径） | 工具封装、create_agent、agent API、会话/重试/日志 | `exp5/agent/`、`app/api/agent.py` |
| **D 前端** | AgentChatView、思考过程展示、响应式、错误提示 | `/agent` 页 |
| **E 测试集成** | 三场景 e2e、10 轮准确率、延迟两口径、跨浏览器 | `exp5/eval/`、点检表 |
| **F 报告统稿** | 闭环架构图、复用点表、问题记录、统稿打包 | 实验报告 + zip |

**并行节奏**：C 与 A/B 课前即开工（工具与数据零依赖）；D 等 C 的信封契约定稿即可用 mock 先行；E 在 C/D 联调后进场；F 全程随手收集截图与数字，不最后补。

---

## 六、报告骨架（任务书"实验报告要求"逐条对位，写时直接抄结构）

1. **成员与分工表**（上表换人名）。
2. **闭环架构图**：实验1 语料/图像 → 实验2 `best.pt` → 实验3 INT8 → 实验4 `/api/v1/*` → 实验5 工具+LLM → 前端 /agent；标注数据流节点（40,376 条语料、4316 张训练图（v2 修复增强）、mAP50 **A2′ 0.992 / INT8 0.990**（clean190）、事件表 6,247 行）。**技术复用点表**：实验1 清洗→5.1.2；实验2 迁移训练思想+消融方法→5.2.2 对比实验；实验3 量化→QLoRA 4bit 与 Ollama Q4；实验4 API/信封/CORS/会话→工具与部署。
3. **Agent 性能评估**：10 轮工具调用准确率（≥90%）；延迟表（文本/图像/多轮 × API/本地Q4，量化前后对比）；三方分类准确率表（joblib vs 零样本 vs LoRA）。
4. **问题与解决**（提前埋好记录位）：QLoRA 显存（4bit+梯度累积8）；工具调用失败（3 次重试+日志）；跨域（CORS 5173）；async 路由同步 httpx 自调用死锁（用内部函数/AsyncClient）；API 限流降级 Ollama。**对比总结**：实验2 小模型微调（全参迁移、收敛快、只能分类）vs 实验5 大模型 QLoRA（参数高效、指令泛化、资源受限可训）。

---

## 七、坑清单（实验1-4 亲测 + 实验5 预判）

1. **torch DLL 崩溃（WinError 1114）**：独立 venv、勿从 Anaconda Prompt 启动（实验1 教训，`docs/CLEANUP_LOG.md`）。
2. **async 路由内同步 httpx 自调用 8000 → 死锁**：工具默认复用 `app/services/` 内部函数；必须 HTTP 时用 `httpx.AsyncClient`。
3. **CORS/端口**：前端 5173（不是任务书模板的 3000）；Agent 合并部署 8000，报告说明与 8001 示意的关系。
4. **防泄漏**：演示与评估只用 `split_test`/test 图像；微调数据抽自 `split_train`，脚本内置断言。
5. **精度口径**：**✅ 已刷新（v2）**——增强缺陷修复重训后统一 clean190 单口径：A1 0.990 / **A2′ 0.992（部署）** / M1′ 0.993 / INT8 0.990（`models/exp2_v2/eval_test190.json`）；旧双口径（0.987/0.988 vs 0.419/0.420）已作废，仅作 erratum 素材。
6. **API key/配额**：`.env` 不入库；API 限流或断网 → `EXP5_LLM_PROVIDER=ollama` 降级演示。
7. **Windows 编码**：脚本统一 UTF-8 读写（`-X utf8`）。
8. **工具误选**：描述写明"输入是图像路径→选 player_detect；输入是文字→选 commentary_classify"；准确率<90% 先改提示词再加路由。
9. **系统代理劫持 httpx（2026-11-08 实测）**：本机开 VPN/Clash 类代理时，Python httpx 默认读取系统代理，会把 localhost 请求和 LLM 调用都绕进代理，造成偶发超时/60 秒慢响应/500。已修：LLM 客户端默认直连（providers.py `trust_env=False`，需要代理时 `.env` 设 `EXP5_LLM_TRUST_ENV=1`）；接口测试脚本同样 `trust_env=False`。队友机器若也开代理，直接受益。

---

## 八、交付物清单（对照打钩）

- [ ] `exp5/data/agent_finetune_data.json`（100 条，任务书命名）
- [ ] `exp5/colab_pkg/` + LoRA adapter + 训练曲线
- [ ] `backend/app/agent/`（providers/tools/graph，**已并入实验4 后端，系统自包含**）+ `exp5/eval/`（准确率/延迟脚本与结果）
- [ ] `app/api/agent.py`（/api/v1/agent/chat）+ 会话表 + 重试日志；Postman 用例
- [ ] `AgentChatView.vue`（/agent，思考过程/错误提示/响应式）
- [ ] （主线，可砍）`worker/commentary/llm.py` 替换 stub
- [ ] 三场景 e2e 截图、10 轮准确率表、延迟两口径表、跨浏览器点检表
- [ ] `report/实验5报告.docx/.pdf` + `实验5_完整代码模型与报告.zip`
