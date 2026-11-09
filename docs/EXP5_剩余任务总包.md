# 实验5 剩余任务总包（交接执行版）

> **收件人**：实验5 执行成员。前序成果（Agent 后端、五工具、契约、全部评估脚本、v2 权重）已完成并在 **git master** 上——本包 = 环境就绪 → 四块任务 → 验收标准 → 资产清单。
> **四份必读文档（都在 git 上）**：`exp5/CONTRACT.md`（接口契约）、`docs/TEAM_PLAN_EXP5.md`（总计划+九章报告骨架）、`exp5/微调线执行手册.md`（微调全流程）、本文件。

---

## 0. 环境就绪（半天）

1. `git pull` master（**权重、分类器、语料外的所有代码文档都在仓库里**，含最新 v2 模型文件）；
2. `exp4/complete_web_system/backend/` 建 venv（Python 3.11/3.12 均可）：`pip install -r requirements-dev.txt`（已含 langchain/openai）；
3. 配 key：复制 `exp5/.env.example` 为 `backend/.env`，填组长私发的 key（ChatAnywhere + `deepseek-v4.1-flash-1017` 已实测可用）；**key 不进 git、不发群**；
4. RAG 语料：**已在 git 里**（`backend/ml/split_train.jsonl`，RAG 工具自动找到；微调造数据用 `backend/ml/split_train.jsonl`、考题用 `split_test.jsonl`）；
5. 启动验证（应全绿）：
   - 冒烟：`.venv\Scripts\python.exe exp5\smoke_agent.py`（3/3 场景）
   - 接口：起 uvicorn 后跑 `exp5\test_agent_api.py`（5/5 用例）
   - 前端：`pnpm install && pnpm dev`，四页 + 视频页正常。

## 1. 前端 /agent 页（1~2 天，任务书 5.4.2）

- 挂载：`frontend/src/views/AgentChatView.vue`，路由 `/agent`，NavBar 增"AI 解说"；
- **照 `exp5/CONTRACT.md` 开发**（含 mock JSON，可先做页面后联调）：POST `/api/v1/agent/chat`，渲染 `result.agent` 气泡 + `result.tool_calls` 过程条（"🔧 球员检测 · 成功 · 146ms"）；
- 错误动作表（契约 §4）：400 表单校验 / 404 提示换说法 / 429 "稍等几秒重试" / 500·504 "请重试"按钮；
- 移动端：气泡 max-width + word-break，复用现有响应式断点；
- **验收**：任务书三场景前端闭环（test 图→人数 / 解说→类别 / 多轮上下文）+ 截图存档。

## 2. 微调线（约 2 天，照 `exp5/微调线执行手册.md` 执行）

- **数据源纠正**：用交接包 `split_train.jsonl`（4 万条解说语料）**不是** 122 篇资讯；100 条练习题 + 10 道考题流程、自检断言全在手册 §1；
- 基线（§2）→ QLoRA 训练（§3，你有 5060 就本地跑，手册的 Kaggle 方案是无卡备选）→ 三方对比表（§4）；
- 产出直接进报告第七章：joblib vs 零样本 vs 微调 准确率表 + loss 曲线。

## 3. 测试线（约 1 天，脚本全部现成）

| 跑什么 | 用什么 | 已有结果 |
|---|---|---|
| 接口 5 用例 | `exp5/test_agent_api.py` | 5/5 ✅ |
| 工具准确率 10 轮 | `exp5/eval/tool_accuracy.py` | 10/10=100% ✅（复测留证） |
| RAG 冒烟 | `exp5/eval/rag_smoke.py` | 2/2 ✅ |
| **延迟两口径表（你要做）** | 同脚本各跑 10 次记均值/P95：中转 vs 官方直连（改 `.env` 的 BASE_URL/MODEL） | 已知：中转偶发 60~180s 慢响应，直连待测 |
| **跨浏览器点检表（你要做）** | Edge/Firefox/移动端视口逐页点检 | — |
| **异常注入（你要做）** | 改错 key→500/504、并发快问→429，验证前端提示 | — |

## 4. 报告：九章课程总报告

骨架与各章分工见 `docs/TEAM_PLAN_EXP5.md` §六（九章表 + 第七章明细）。要点：前六章从四份旧报告提炼（`report/` 有 v1+v2）；第七章数字素材已备齐：**A2′ 0.992 / INT8 0.990（clean190）、工具准确率 100%、接口回归 5/5、视频 56ms/帧、v2 权重置信度 0.51→0.89、问题清单（代理劫持修复等）**。

## 5. 可选加分（时间富余再做）

LLM 解说替换视频桩：实现 `worker/commentary/llm.py`（继承 `CommentaryService`，复用 `app/agent/providers.py` 的模型客户端），Worker 配置切换；演示效果=视频页解说文案变 LLM 生成。

## 6. 资产清单

- **git 上有（pull 即得）**：全部代码、五工具 Agent 后端、契约/计划/手册、评估脚本与结果、v2 权重（best.pt / a2v2_int8_val173.onnx）、文本分类器、**解说语料（backend/ml/split_train|test.jsonl）**、报告 v1+v2、图 1-7；
- **需要自己准备**：大模型 API key（你已有的 DeepSeek 官方 key 直接用，照 `.env.example` 填 `backend/.env`；官方直连延迟优于中转）；
- **坑速查**：`docs/TEAM_PLAN_EXP5.md` §七 9 条（代理劫持、Anaconda DLL、CORS、防泄漏、精度口径等）。

## 7. 顺序建议

环境（0.5 天）→ 前端页与微调数据**并行**（前端 1-2 天 / 数据 1 天）→ 微调上机（半天等训练）→ 联调三场景（0.5 天）→ 测试三表（1 天）→ 报告汇总。**总有效工作量约 5~6 天一人。**
