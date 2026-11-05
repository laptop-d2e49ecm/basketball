# 第三版发布检查记录

日期：2026-11-05。本次从待发布的 `exp4/complete_web_system/` 目录执行检查，源码对应 `frontend-v3.0.0`。

| 检查 | 结果 | 覆盖范围 |
|---|---|---|
| 后端 pytest | 12 项通过 | 坐标处理、演示 API 正常与异常路径；使用替身模型 |
| 前端单元测试 | 3 项通过 | Vue 坐标转换函数 |
| 类型检查与生产构建 | 通过 | vue-tsc、Vite；主 JS 约 1.56 MB，仍有大包提示 |
| 响应式布局 | 36 项通过 | 4 页面 × 3 视口 × 3 浏览器 |
| 最近任务导航 | 9 项通过 | 检测/文本/图文页返回最近任务，含刷新 |
| 上传与分析交互 | 15 项通过 | 等待界面与进度、轮询回退、上传失败重试、分析失败、清空后重传与迟到响应隔离 |

浏览器合计 **60 项通过**，Edge、WebKit、Firefox 各 20 项。详细记录见 [browser-v3-results.json](browser-v3-results.json)。视口为 390×844、768×1024、1440×900；上传等待界面还验证了移动端宽度。

这些浏览器用例使用固定 API / WebSocket 响应验证界面行为，不代表三浏览器都进行了真实模型推理。Edge 使用 Chromium 内核，WebKit 不等同于 macOS Safari 实机。本机 Firefox 子进程有启动问题，本次仅在临时测试进程关闭内容沙箱并使用软件渲染，未修改系统配置；其他机器可先使用默认 Playwright Firefox 配置运行。

## 复现

```powershell
Set-Location .\backend
.\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
pnpm test:unit
pnpm build
pnpm exec playwright install
pnpm test:e2e
```

三个浏览器各执行 `responsive.spec.ts` 12 项、`navigation.spec.ts` 3 项和 `analysis-progress.spec.ts` 5 项。测试服务器与模型服务分离，不需要加载模型。

## 已完成的真实后端验证

- 36.04 秒 CPU 视频基线：抽帧间隔 2、450/450 采样帧、平均推理 25.09 ms、Worker 处理 17.285 秒；见 [VIDEO_BASELINE.md](../reports/VIDEO_BASELINE.md)。
- 本地 Celery 5.6.3 + Redis 5.0.14.1、Windows solo/CPU、短视频任务：pending → running → ready，25 条检测、1 条事件；提交至观察到完成 4.986 秒。见 [celery-smoke.json](../reports/celery-smoke.json)。这是单任务连通性验证，未覆盖分布式并发或故障恢复。
- Edge 调用真实 API，从提交到结果可见，每项预热 1 次后测量 10 次。检测均值/P95 131.33/145.50 ms，文本 44.90/47.10 ms，图文演示 132.17/144.50 ms；不含初始页面加载、选文件和模型启动。见 [browser-display.json](../reports/browser-display.json)。
- 实验一图片 `samples/images/v_-6Os86HzwCs_c001__f000025.jpg` 实际检测响应保存在 [detect-response.json](../reports/detect-response.json)。

这些真实推理数据为本机先前实测记录，本次发布重新执行的是上表的构建、单元和界面检查。
