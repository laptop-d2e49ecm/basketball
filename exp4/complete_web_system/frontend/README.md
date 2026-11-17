# 前端（最终版）

Vue 3 + TypeScript + Vite。开发代理把 `/api`、`/ws` 转发到 `127.0.0.1:8000`。

工作台统一在 `/`（`src/views/WorkspaceView.vue` + `src/workspace.css`）：首页导入 MP4（可填视频名/对阵/比分）→ 分析进度 → 结果工作台（画面帧、检测框回放、事件解说带、人数曲线、整场 AI 解说、导出、右侧 AI 对话）；`/recent` 为最近任务，`/analyzing/:taskId`、`/tasks/:taskId` 为任务页。旧的 `/video`、`/video-v3`、`/agent`、`/detect`、`/text`、`/match` 入口一律重定向回 `/`。

> **音频待测试**：解说语音（播放器上的“解说开/关”、导出面板的“朗读解说”和“下载 MP3”，后端 `GET /api/v1/tasks/{task_id}/narration/audio`）已完成前端接入，但尚未完成端到端测试——TTS 服务可用性、音频与事件时间轴是否同步、浏览器自动播放受限时的朗读回退都待验证。当前验收以文本解说为准，音频标注为“待测试”。

通常使用仓库根目录 `一键启动.bat`（或上级目录 `start_project_v3.bat`）一键启动。单独开发可运行 `pnpm install`、`pnpm dev`；构建用 `pnpm build`（含 vue-tsc 类型检查），浏览器测试用 `pnpm test:e2e`（`e2e/workspace.spec.ts`，使用模拟 API，不依赖真实后端）。

主要文件：

- `src/views/WorkspaceView.vue`、`src/workspace.css`：工作台页面与样式。
- `src/api/client.ts`：任务、进度、事件、解说和对话请求。
- `src/views/VideoNarration.vue`：跟随视频播放的解说语音（音频待测试）。
- `src/views/NarrationSpeech.vue`：导出面板中的整场解说朗读（音频待测试）。
