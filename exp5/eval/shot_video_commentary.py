# -*- coding: utf-8 -*-
"""给“视频解说 LLM 化”抓两张验收截图：视频工作台解说面板、/agent 逐事件播报。"""
from __future__ import annotations

import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5173"
OUT = pathlib.Path(r"C:\sofeware\AI Api\dsh workspace\fish\work\basketball-git\report\figures")
TASK = sys.argv[1] if len(sys.argv) > 1 else ""

OUT.mkdir(parents=True, exist_ok=True)


def shoot_video(page) -> None:
    page.goto(f"{BASE}/courtvision.html", wait_until="networkidle", timeout=60000)
    page.click("#recentNav")
    page.wait_for_selector(".task-item", timeout=30000)
    row = page.locator(".task-item", has_text=TASK).first
    row.locator("button.task-open").click()
    page.wait_for_selector(".event-row", timeout=60000)
    page.wait_for_timeout(6000)  # 等视频预览与解说面板稳定
    page.screenshot(path=str(OUT / "exp5_video_commentary.png"), clip={"x":250,"y":60,"width":1190,"height":748})
    print("video shot ok, events =", page.locator(".event-row").count())


def shoot_agent(page) -> None:
    page.goto(f"{BASE}/agent", wait_until="networkidle", timeout=60000)
    box = page.locator("textarea").first
    box.fill(f"{TASK} 给这个视频配解说")
    box.press("Enter")
    page.wait_for_timeout(12000)
    page.screenshot(path=str(OUT / "exp5_agent_video_narration.png"), clip={"x":250,"y":60,"width":1190,"height":640})
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
