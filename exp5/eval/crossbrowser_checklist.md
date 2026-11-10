# 跨浏览器点检记录

> 目的：任务书 5.4.3「在 Chrome、Firefox、移动端浏览器验证界面适配与功能稳定性」。

## 1. Chromium（Microsoft Edge 157，Playwright 自动化）

| 页面 | 检查 | 结果 |
|---|---|---|
| `/agent` | 空态、发问、气泡、工具过程条 | ✅ |
| `/agent` 场景1 图像 | `f000005` → 10 名球员 | ✅ `agent_01_image.png` |
| `/agent` 场景2 文本 | 抢断句 → 抢断 | ✅ `agent_02_text.png` |
| `/agent` 场景3 多轮 | 概念问答→追问 `f000025` | ✅ `agent_03_multiturn.png` |
| `/agent` LoRA 后端 | 分类句 → 显示"后端：实验5 微调 LoRA" | ✅ `agent_06_lora_backend.png` |
| `/agent` 错误态 | 假 key → "请重试"按钮 | ✅ `agent_05_error_retry.png` |
| `/video-v3` `/detect` `/text` `/match` | 四页渲染 | ✅ `page_*.png` |
| 移动端 390×844 | 气泡换行、输入区堆叠 | ✅ `agent_04_mobile.png` |

## 2. Firefox 160（本机安装版，`firefox --headless --screenshot`）

| 页面 | 结果 | 截图 |
|---|---|---|
| `/agent` 1440×900 | ✅ 布局与 Edge 一致（导航/气泡区/快捷提问/会话卡齐全） | `firefox_agent.png` |
| `/agent` 390×844 | ✅ 单列布局，输入区堆叠，无横向溢出 | `firefox_agent_mobile.png` |
| `/detect` | ✅ 渲染正常 | `firefox_detect.png` |
| `/text` | ✅ 渲染正常 | `firefox_text.png` |
| `/match` | ✅ 渲染正常 | `firefox_match.png` |

## 2b. Firefox 交互（用户手动验证，2026-11-10 23:02）

- 输入 000005 这张图里有几个球员？ → 回复"检测到 10 名球员，平均置信度 0.89，80.5ms"
- 工具条显示"球员检测 · 成功 · 81ms"，本轮 4.4s，会话 ID sess_acc8b21bcb2
- 截图存档：
eport/figures/firefox_agent_chat.png

## 3. 未能自动化的部分（如实记录）

**Firefox 的"交互"（输入 + 点发送）无法在本环境自动化**：

- Playwright 的 firefox 构建：启动 `exit 1`（超时 180s）；
- Selenium + geckodriver（Marionette）：新建会话时 `Process unexpectedly closed with status 1`；
- 但 **`firefox --headless --screenshot` 可用**（2 秒出图），说明 Firefox 本身能跑、能渲染，限制在自动化协议这条通道上。

**交互已由用户手动验证通过**（见 2b）。当时给出的手动清单：

1. 用 Firefox 打开 `http://127.0.0.1:5173/agent`
2. 输入 `f000005 这张图里有几个球员？` → 发送
3. 看到回答 + "🔧 球员检测 · 成功" → 打勾

## 4. 结论

- **渲染层**：Chromium / Firefox / 移动端视口 三套都已验证，布局一致；
- **交互层**：Chromium 全流程自动化通过；Firefox 需手动确认一次（约 1 分钟）；
- WebKit/Safari 未测（无 macOS 环境），报告里如实写。
