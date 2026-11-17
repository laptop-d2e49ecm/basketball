# -*- coding: utf-8 -*-
"""给“视频解说 LLM 化”抓两张验收截图：视频工作台解说面板、/agent 逐事件播报。

用法：python exp5/eval/shot_video_commentary.py [工作台任务名关键词] [agent 任务编号]
截图默认写入仓库 report/figures（可用环境变量 REPORT_FIG_DIR 覆盖），
需要 5173（前端）与 8000（后端）服务已启动。
"""
from __future__ import annotations

import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5173"
_DEFAULT_OUT = pathlib.Path(__file__).resolve().parents[2] / "report" / "figures"
OUT = pathlib.Path(os.environ.get("REPORT_FIG_DIR") or _DEFAULT_OUT)
VIDEO_TASK = sys.argv[1] if len(sys.argv) > 1 else ""
AGENT_TASK = sys.argv[2] if len(sys.argv) > 2 else VIDEO_TASK

OUT.mkdir(parents=True, exist_ok=True)


def shoot_video(page) -> None:
    page.goto(f"{BASE}/courtvision.html", wait_until="networkidle", timeout=60000)
    page.click("#navRecent")
    page.wait_for_selector("#taskList .tb", timeout=30000)
    row = page.locator("#taskList .tb", has_text=VIDEO_TASK).first
    row.locator("button.open-t").click()
    page.wait_for_selector(".event-row", timeout=60000)
    page.wait_for_timeout(8000)  # 等视频预览、画面帧条与整场解说面板稳定
    page.screenshot(path=str(OUT / "exp5_video_commentary.png"))
    print("video shot ok, events =", page.locator(".event-row").count())


def shoot_agent(page) -> None:
    page.goto(f"{BASE}/agent", wait_until="networkidle", timeout=60000)
    box = page.locator("textarea").first
    box.fill(f"{AGENT_TASK} 给这个视频配解说")
    box.press("Enter")
    page.wait_for_timeout(12000)
    page.screenshot(path=str(OUT / "exp5_agent_video_narration.png"))
    print("agent shot ok")


def main() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()
        shoot_video(page)
        page2 = ctx.new_page()
        shoot_agent(page2)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
