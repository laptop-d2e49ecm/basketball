# 实验5 交付记录（段 7）

日期：2026-11-11　执行人：项目组（AI 助手协助）

## 一、本次交付做了什么

| 编号 | 内容 | 产物 |
|---|---|---|
| 1 | 一键启动 / 停止脚本 | `start_exp5.bat`、`stop_exp5.bat`、`scripts/run/launch.py`、`scripts/run/run_vite.mjs` |
| 2 | 冷启动验收（先停后起，无残留进程） | 见第二节记录 |
| 3 | 交付包打包与哈希校验 | `dist/实验5_完整代码模型与报告.zip`（81.7 MB，666 个文件，SHA256 全部核对通过） |
| 4 | 交付说明 | `docs/交付说明-实验5.md` |

## 二、验收记录（2026-11-11 11:15 前后）

**冷启动**：先执行 `stop_exp5.bat` 确认 8000/5173 均无监听，再执行 `start_exp5.bat`。

脚本输出（节选）：

```
[1/4] 检查端口占用 ...  [free] 端口 8000 / [free] 端口 5173
[2/4] 启动后端 ...      [ready] http://127.0.0.1:8000/api/v1/health
[3/4] 启动前端 ...      [ready] http://127.0.0.1:5173/
[4/4] 模型自检 ...
{"status":"ok","detector_loaded":true,"text_clf_loaded":true,"backend_mode":"worker",...}
[ok] 两个模型均已加载
```

**页面可用性**：`/`、`/agent`、`/detect`、`/text`、`/match`、`/video-v3` 全部 200；
`/api/v1/health`、`/api/v1/tasks` 200。

**Agent 对话**：

- 首问「来一句解说」→ `code=0`，provider=api，2.8 s；
- 工具问「f000005 这张图里有几个球员？」→ 调用 `player_detect`，
  返回「检测到 10 名球员，平均置信度 0.89，推理 51.87 ms」。

## 三、已知限制

- 基座 `Qwen3-1.7B`（约 4 GB）不入包，需按说明下载；
- Python 虚拟环境与 `node_modules` 不入包，换机需按 requirements / pnpm install 重建；
- Agent 依赖外网 API（DeepSeek），断网仅本地 LoRA 分类可用；
- 交付包内的 `代码/` 是仓库快照，直接双击 bat 会因缺少 `.venv`、`node_modules` 而给出明确报错——
  在本机请使用仓库目录下的 `start_exp5.bat`。

## 四、复现命令

```bat
:: 启动
start_exp5.bat
:: 停止
stop_exp5.bat
:: 校验交付包
certutil -hashfile 实验5_完整代码模型与报告.zip SHA256
```

## 五、追加任务：视频解说 LLM 化（2026-11-12）

| 项 | 结果 |
|---|---|
| worker/commentary/llm.py | 新增，含 10 s 硬超时、同键 5 s 去重、单任务调用上限、失败回退 |
| 开关 | BASKETBALL_COMMENTARY=stub\|llm，.env.example 同步 |
| demo 实测 | 20 事件全部 LLM 文案；整任务 8.4 s（stub）→ 29.5 s（llm） |
| 容错 | 错 key → 401 → 2 次回退、任务 ready、WARN 日志 |
| 聊天页 | SYSTEM_PROMPT 第 5 条扩展，任务编号 + “给这个视频配解说” → 逐事件播报；工具准确率仍 10/10 |
| 测试 | pytest -q 12 passed |
| 报告 | 新增 7.5 节、图 7-3/7-4、表 7-5；33 页，目录 57 条逐条核对通过 |
