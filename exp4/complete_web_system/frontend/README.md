# 第三版前端

Vue 3 + TypeScript + Vite + Ant Design Vue。开发代理把 `/api`、`/ws` 转发到 `127.0.0.1:8000`。

默认工作台为 `/video-v3`，通过 `src/views/VideoV3View.vue` 加载 `public/courtvision.html`；`/` 和 `/video` 自动跳转到工作台。其他页面是 `/detect`、`/text`、`/match`。

通常使用上级目录 `start_project_v3.bat` 一键启动。单独开发可运行 `pnpm install`、`pnpm dev`；构建用 `pnpm build`，单元测试用 `pnpm test:unit`，浏览器测试用 `pnpm test:e2e`。

等待界面使用实际任务进度，支持 WebSocket 通知及 REST 轮询。历史任务入口、清除后重传和错误提示用例见 `e2e/analysis-progress.spec.ts`；导航与响应式检查分别在 `navigation.spec.ts`、`responsive.spec.ts`。

本次后端增加可选表单字段 `video_name`。使用上级目录的配套后端，才能保存视频名称并管理历史任务。
