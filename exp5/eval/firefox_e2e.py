# -*- coding: utf-8 -*-
"""段5.3：用 Selenium + 系统 Firefox 跑 /agent 一次真实问答（跨浏览器功能验证）。

与静态截图不同，这里是真的输入、点发送、等回答，验证 Firefox 下的交互可用。
产物：report/figures/firefox_agent_chat.png
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "report/figures/firefox_agent_chat.png"
URL = "http://127.0.0.1:5173/agent"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--width=1440")
    opts.add_argument("--height=900")
    # 复用已启动的 geckodriver（环境里 Selenium 的 Service 启动会 exit 64）
    driver = webdriver.Remote(command_executor="http://127.0.0.1:4444", options=opts)
    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 60)
        box = wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "textarea.composer-input"))
        box.send_keys("f000005 这张图里有几个球员？")
        driver.find_element(By.XPATH, "//button[contains(., '发送')]").click()

        def answered(d):
            bubbles = d.find_elements(By.CSS_SELECTOR, ".turn-agent .bubble-text")
            if not bubbles:
                return False
            text = bubbles[-1].text.strip()
            return bool(text) and "正在思考" not in d.find_element(By.CSS_SELECTOR, ".turn-agent .bubble").text

        wait.until(answered)
        time.sleep(0.5)
        answer = driver.find_elements(By.CSS_SELECTOR, ".turn-agent .bubble-text")[-1].text.strip()
        tools = [e.text.strip() for e in driver.find_elements(By.CSS_SELECTOR, ".tool-chip")]
        driver.save_screenshot(str(OUT))
        print(f"URL: {driver.current_url}")
        print(f"UA: {driver.execute_script('return navigator.userAgent')[:90]}")
        print(f"回答: {answer[:120]}")
        print(f"工具条: {tools}")
        print(f"截图: {OUT}")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
