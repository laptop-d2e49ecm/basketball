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

## 音频（解说语音）

音频与新下载的 `.new` 版本一致，使用 edge-tts 云健音色：普通句 +10% 语速，感叹句 +35% 语速、+25Hz 音调，输出 MP3。在线服务不可用时提示重试。播放器支持分段播放，导出面板支持整场朗读和 MP3 下载；旧音色缓存会自动重新合成。

解说稿按各段覆盖的视频时长分配篇幅（目标每秒约 5.5 个汉字），围绕有依据的动作和画面细节展开，首段从视频开头开始、末段覆盖视频结尾。略短的音频可适度放慢，最低为合成速度的 0.8 倍，以减少段间空白；素材证据过少或在线合成未就绪时仍可能出现停顿。已有任务点击“重新生成解说”应用新规则。

已验证在线语音合成、后端自动化测试与前端构建；完整比赛的听感和同步效果仍需结合实际视频验收。

## 聊天附图

AI 对话输入框旁提供“＋”。点击后进入选帧模式，在左侧“画面帧”中连续选择（最多 6 张），预览显示在输入框上方，可逐张移除。选帧不会发送问题，只有点击“发送”才会把文字和附图一起交给 AI；只发送图片时默认分别询问球员人数。再次点击“＋”退出选帧模式，普通点击画面仍跳转播放位置。

图片会保存到对应视频任务的 `chat_images/`，对话历史保留预览；清空该任务时随任务文件一同删除。后端校验图片内容并重新编码为 JPEG，再将内部路径交给 `player_detect` / `image_text_match` 工具，用户无需手动填写路径。这两项工具分别提供球员检测及篮球内容相关性判断，均不依赖另行配置的视觉大模型。

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
