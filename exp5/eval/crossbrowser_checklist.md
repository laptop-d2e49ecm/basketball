# 跨浏览器点检记录

> 目的：任务书 5.4.3「在 Chrome、Firefox、移动端浏览器验证界面适配与功能稳定性」。
> 自动化环境说明：本会话的沙箱里 **Firefox 无法启动**（Playwright 的 firefox 构建 exit 1、
> 官方 `firefox --headless --screenshot` 同样 exit 1、无输出），属于**运行环境限制**，与页面无关；
> Chromium（本机 Edge）自动化通过。Firefox 一项改为"本机手动点检"，清单见文末。

## 1. Chromium（Microsoft Edge 157，Playwright 自动化）

| 页面 | 检查 | 结果 |
|---|---|---|
| `/agent` | 空态、发问、气泡、工具过程条 | ✅ |
| `/agent` 场景1 图像 | `f000005` → 10 名球员 | ✅ 截图 `agent_01_image.png` |
| `/agent` 场景2 文本 | 抢断句 → 抢断 | ✅ 截图 `agent_02_text.png` |
| `/agent` 场景3 多轮 | 概念问答→追问 `f000025` | ✅ 截图 `agent_03_multiturn.png` |
| `/agent` LoRA 后端 | 分类句 → 显示"后端：实验5 微调 LoRA" | ✅ 截图 `agent_06_lora_backend.png` |
| `/agent` 错误态 | 假 key → "请重试"按钮 | ✅ 截图 `agent_05_error_retry.png` |
| `/video-v3` `/detect` `/text` `/match` | 四页渲染 | ✅ 截图 `page_*.png` |
| 移动端 390×844 | 气泡换行、输入区堆叠 | ✅ 截图 `agent_04_mobile.png` |

## 2. Firefox —— 本机手动点检清单（约 5 分钟）

> 你装好 Firefox 后，双击启动前后端（或告诉我，我把服务拉起来），然后：

1. 打开 `http://127.0.0.1:5173/agent`
   - [ ] 页面正常渲染，左侧导航有"AI 解说"
   - [ ] 输入 `f000005 这张图里有几个球员？`，点发送
   - [ ] 3 秒内出现回答 + "🔧 球员检测 · 成功"
   - [ ] 点工具条，能展开"入参/结果"
2. 打开 `/detect`、`/text`、`/match`
   - [ ] 三个页面布局与 Edge 一致（没有错位/溢出）
3. 窗口缩到手机宽度（拖窄或 F12 设备模拟 390px）
   - [ ] `/agent` 气泡不溢出、输入框不超出屏幕

勾完把结果告诉我（或截两张图），我把这一段补进报告第八章。

## 3. 已知限制

- Firefox 的自动化验证**未完成**（环境限制）；
- WebKit/Safari 未测（无 macOS 环境）；
- 移动端是**视口模拟**，不是真机。
