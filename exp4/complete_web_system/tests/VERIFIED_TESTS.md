# 已通过的构建与测试记录

本记录对应本次集成工作区中的前后端源码。

- 后端 pytest：12 项通过，覆盖坐标处理与演示 API。
- 前端单元测试：3 项通过。
- 前端生产构建：通过。
- 浏览器响应式验收：36 项通过，覆盖任务书要求的三浏览器——Edge Chromium、WebKit（Safari 内核）与 **Firefox（2026-11-02 补测，12/12 通过）**；每浏览器覆盖 /video、/detect、/text、/match 四页及 xs、md、xl 三种视口（断言：无横向滚动 + 栅格分栏比例）。

复现命令见本目录 README.md。浏览器验收使用 Playwright；运行前需安装项目依赖及对应浏览器（`pnpm exec playwright install firefox` 等）。响应式用例内置 `/api/v1/**` 路由 mock，无需启动后端。

## 分浏览器明细

| 浏览器 | 引擎 | 用例数 | 结果 | 日期 |
|---|---|---|---|---|
| Edge（channel=msedge） | Chromium | 12 | ✅ 全过 | 2026-11-02（集成方） |
| Desktop Safari | WebKit | 12 | ✅ 全过 | 2026-11-02（集成方） |
| Desktop Firefox | Gecko | 12 | ✅ 全过 | 2026-11-02（图像/文本侧补测，`pnpm exec playwright test --project=firefox`） |
