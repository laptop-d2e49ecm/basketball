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

## 启动入口精简检查（2026-11-06）

当前目录只保留 `start_project_v3.bat` 和 `stop_project.bat`，启动与关闭逻辑已内置。两个脚本的 Windows PowerShell 语法解析通过，并在包含中文、空格、感叹号和括号的隔离目录中完成以下 5 项检查：

- 缺少后端依赖时，启动 BAT 正确定位项目目录并返回错误。
- 没有服务清单时，关闭 BAT 正常退出。
- 已有服务复用流程进入 `/video-v3`，无需独立 PS1；该项替换了服务探测和浏览器打开操作，不属于真实服务启动验证。
- 关闭 BAT 能终止测试专用的、进程身份匹配的后台进程。
- 进程启动时间与清单不符时，关闭 BAT 保留该进程。

本次检查没有关闭正在使用的项目服务，也没有重新进行模型推理或浏览器功能测试。

## 真实视频完整流程联调（2026-11-06）

使用源码提交 `cec6547bd893fe96a38414e590ef3699b26f82bb`，在 Microsoft Edge 156.0.4314.42 中连接真实 FastAPI 后端与独立 Worker，完成 36.04 秒篮球视频的完整流程联调。本轮没有修改应用代码，没有替换 API 或 WebSocket 响应。

- CPU、抽帧步长 2，完成 450 / 450 个采样帧，生成 19 条启发式事件。
- Worker 处理耗时 35.008 秒；选择文件开始上传至页面结果可见耗时 36.446 秒。这是单次视频任务结果，不是多次运行均值。
- 13 项检查通过，覆盖上传、真实进度、检测框、完整播放、事件定位后暂停、手动继续播放、历史回放及清空后重新选择视频等。
- 这是 Edge、单视频、独立 Worker 模式的真实联调；与前文 60 项模拟接口界面测试分别记录，不代表三种浏览器均完成真实视频流程，也不新增 GPU、Celery、多用户并发或转码分支的验收结论。

完整说明与复测经过见 [联调验收记录](../reports/video-integration-20261106/README.md)；原始请求、响应、检查和耗时见 [integration-result.json](../reports/video-integration-20261106/integration-result.json)，截图、检测记录、服务日志、执行脚本及追踪保存在同一目录。记录中保留被测源码哈希，证据文件校验见 [manifest.json](../reports/video-integration-20261106/manifest.json)。
