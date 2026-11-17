# 篮球赛事视频分析与 AI 解说

本目录是当前运行程序。前端首页将视频上传、分析进度、检测框、关键事件、整场解说和当前视频的 AI 对话放在同一个工作台。历史任务可从“最近任务”打开。

## 首次安装

需要 Python 3.11 或 3.12、Node.js 20.19+（或 22.12+）和 pnpm。在本目录的 PowerShell 中运行：

```powershell
Set-Location .\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Set-Location ..\frontend
pnpm install
```

视频分析和解说需要模型与服务配置。大模型参数写在 `backend/.env`，参照仓库 `exp5/.env.example`；不要把密钥提交到仓库。未配置大模型时，上传和视觉分析仍可使用，但整场 AI 解说和任务对话不能正常生成。

## 启动与使用

双击 `start_project_v3.bat`，等待 API、Worker、前端启动后，浏览器打开 `http://127.0.0.1:5173/`。关闭服务使用 `stop_project.bat`。API 文档在 `http://127.0.0.1:8000/docs`。

1. 在首页导入 MP4 视频并确认分析。
2. 在进度页等待，或从“最近任务”返回任务。
3. 结果页查看视频、检测框、事件、解说；可针对当前任务向 AI 提问。
4. 整场解说失败时可在结果页重新生成；已完成任务可从最近任务删除。

原视频用于模型推理；浏览器不支持其编码时，后端另行生成兼容预览。事件和解说以分析结果为依据，模型未证实的进球、比分、姓名等不应作为确定事实展示。

## 音频（解说语音）状态：待测试

解说语音功能已接入前端（播放器上的“解说开/关”跟随视频播放、导出面板的“朗读解说”和“下载 MP3”，后端接口为 `GET /api/v1/tasks/{task_id}/narration/audio`），但**尚未完成端到端测试**：真实 TTS 服务是否可用、音频与视频关键事件的时间轴是否对齐、浏览器自动播放被拦截时的浏览器朗读回退是否正常，都还没有在有声环境下验收。当前请以文本解说为准，音频标记为“待测试”。

## 主要文件

- `frontend/src/views/WorkspaceView.vue`、`frontend/src/workspace.css`：当前前端工作台。
- `frontend/src/api/client.ts`：任务、事件、解说和对话请求。
- `backend/app/api/tasks.py`：上传、任务状态、预览、事件和解说接口。
- `backend/worker/`：视频检测、跟踪、动作与事件处理。
- `backend/app/api/agent.py`、`backend/app/db/agent_sessions.py`：任务关联的 AI 对话与历史记录。
- `backend/app/tts.py`：整场解说文本的音频合成；接口为 `GET /api/v1/tasks/{task_id}/narration/audio`。

## 检查

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest tests -q
Set-Location ..\frontend
pnpm build
pnpm test:e2e
```

前端交互测试使用模拟 API；真实视频分析仍需在本机配置模型和大模型服务后单独联调。
