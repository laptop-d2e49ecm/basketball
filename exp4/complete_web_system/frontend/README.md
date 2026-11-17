# 前端（最终版）

Vue 3 + TypeScript + Vite + Ant Design Vue。开发代理把 `/api`、`/ws` 转发到 `127.0.0.1:8000`。

默认工作台为 `/video-v3`，通过 `src/views/VideoV3View.vue` 加载 `public/courtvision.html`（深色控制台为实际运行页面）；`/` 和 `/video` 自动跳转到工作台，`/agent` 为 AI 解说对话页（AgentChatView.vue）。

通常使用仓库根目录 `一键启动.bat`（或上级目录 `start_project_v3.bat`）一键启动。单独开发可运行 `pnpm install`、`pnpm dev`；构建用 `pnpm build`（含 TypeScript 检查），浏览器测试用 `pnpm test:e2e`。

等待界面使用实际任务进度，支持 WebSocket 通知及 REST 轮询。历史任务入口、清除后重传和错误提示用例见 `e2e/analysis-progress.spec.ts`；导航与响应式检查分别在 `navigation.spec.ts`、`responsive.spec.ts`。

上传表单的可选字段（`video_name`、`team1`、`team2`、`score1`、`score2`）由配套后端保存；对阵与比分作为解说可信事实注入。
