# -*- coding: utf-8 -*-
"""任务 1.1.2：非结构化文本数据获取（合规网页爬取）。

内置合规检查（任务书"重点与难点"第 3 条）：
1. 爬取前自动检查目标站点 robots.txt，被 Disallow 的 URL 直接跳过；
2. 控制请求频率（默认 2 秒/次），设置真实 UA 标识课程作业用途；
3. 只保留 <p>/<h1>-<h3>/<li> 中的正文文本。

使用前：把 TARGET_URLS 替换为小组选定并确认可合规爬取的页面列表。
输出：data/raw/texts/ 下每页一个 .txt（正文）+ 一个 .jsonl（{"text":...}，供
Data-Juicer 流水线直接使用）+ crawl_meta.json（来源记录）。
"""
import argparse
import json
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# 合规站点（已核对 robots.txt，2026-10-04）：
# - sports.sina.com.cn：robots.txt 为空（200 无规则）= 允许全部，文章即在该域下
# - news.zhibo8.com：robots.txt 返回 404 = 按惯例视为允许抓取（服务端渲染，资讯较新）
# - www.163.com：robots.txt 返回 403，Python RobotFileParser 按保守策略视为全部禁止，
#   故不爬取网易文章（sports.163.com 虽全站允许，但正文均发布在 www.163.com 域）
TARGET_URLS = [
    # 新浪体育 NBA（历史文章，2024-03 ~ 2025-01，来自频道页静态链接）
    "https://sports.sina.com.cn/basketball/nba/2024-03-28/doc-inapvtrw3705419.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-28/doc-inapvtrw3713967.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-28/doc-inapvtrw3718412.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-28/doc-inapvtsa2594993.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-28/doc-inapvtsa2605572.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-28/doc-inapvxxt4634651.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-29/doc-inapyawu2604896.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-29/doc-inapyawu2613857.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-30/doc-inaqafvw3719481.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-03-27/doc-inaptkkx5821640.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-04-05/doc-inaqtytx9912530.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-04-15/doc-inarwcea7237967.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-04-30/doc-inatqssz2351269.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-05-20/doc-inavvkee5431056.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-07-16/doc-inceikzw1370844.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-08-09/doc-inchywqs6031958.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-09-20/doc-incpvpnf0618769.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-10-02/doc-increuyq8299885.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-10-25/doc-incttxhc1733327.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-11-03/doc-incuuaza4384305.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-11-12/doc-incvupac1635814.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-11-21/doc-incwvcmn4622553.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-12-01/doc-incxxsmq9870187.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-12-09/doc-incyvtfx2784392.shtml",
    "https://sports.sina.com.cn/basketball/nba/2024-12-22/doc-ineaiiym4236565.shtml",
    "https://sports.sina.com.cn/basketball/nba/2025-01-02/doc-inecpzyf2530987.shtml",
    "https://sports.sina.com.cn/basketball/nba/2025-01-11/doc-ineeqsia4943748.shtml",
    "https://sports.sina.com.cn/basketball/nba/2025-01-21/doc-ineftfhz8681937.shtml",
    # 直播吧 NBA（当日最新，2026-10-04，来自 news.zhibo8.com/nba/ 版块页）
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c9c0d5947native.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c942c2e4bnative.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c7fd3be65native.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c7e492d4dnative.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c7491c62dnative.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c6bd7ab2enative.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c60c6ecefnative.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c5f5588a1native.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c5c20d853native.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c511061b8native.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c500e2cc2native.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c446a332cnative.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c3527805enative.htm",
    "https://news.zhibo8.com/nba/2026-10-04/6ac1c9f1d85b0native.htm",
]

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "texts"
HEADERS = {
    # HTTP 头只允许 latin-1，注释里说明用途即可，勿放中文
    "User-Agent": "Mozilla/5.0 (compatible; BasketballCourseBot/1.0; course-work)"
}


def robots_allows(url: str) -> bool:
    """检查目标站点 robots.txt 是否允许抓取该 URL。"""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception as e:  # robots.txt 不存在或网络异常时保守处理：允许但记录
        print(f"[!] 读取 robots.txt 失败（{e}），默认按允许处理: {robots_url}")
        return True
    return rp.can_fetch(HEADERS["User-Agent"], url)


def extract_text(html: str) -> str:
    """提取正文段落文本（标题 + 段落 + 列表项）。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
        tag.decompose()
    parts = []
    for tag in soup.select("h1, h2, h3, p, li"):
        text = tag.get_text(" ", strip=True)
        if len(text) >= 10:  # 过滤导航、广告等碎片
            parts.append(text)
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="合规爬取篮球资讯文本")
    parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--urls-file", default="", help="URL 列表文件（每行一个）；不填则用顶部 TARGET_URLS")
    args = parser.parse_args()

    urls = TARGET_URLS
    if args.urls_file:
        from pathlib import Path as _P
        urls = [ln.strip() for ln in _P(args.urls_file).read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")]
    if not urls:
        print("[!] 没有 URL：请编辑 TARGET_URLS 或用 --urls-file 提供列表文件。")
        return
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_list = []
    jsonl_path = out_dir / "all_pages.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as jsonl:
        for i, url in enumerate(urls):
            if not robots_allows(url):
                print(f"[SKIP] robots.txt 禁止: {url}")
                continue
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
            except Exception as e:
                print(f"[FAIL] {url}: {e}")
                continue
            # 新浪等站点为 GBK 编码且响应头未给 charset，requests 会错按 latin-1 解码
            if resp.encoding is None or resp.encoding.lower() in ("iso-8859-1", "ascii"):
                resp.encoding = resp.apparent_encoding or "utf-8"

            text = extract_text(resp.text)
            if len(text) < 50:
                print(f"[SKIP] 正文过短({len(text)}字): {url}")
                continue

            stem = urlparse(url).path.strip("/").replace("/", "_")[-80:] or f"page_{i}"
            txt_path = out_dir / f"{stem}.txt"
            txt_path.write_text(text, encoding="utf-8")
            jsonl.write(json.dumps({"text": text, "url": url}, ensure_ascii=False) + "\n")

            meta_list.append(
                {"url": url, "chars": len(text), "file": txt_path.name, "crawled_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            )
            print(f"[OK] {url} -> {txt_path.name}（{len(text)} 字）")
            time.sleep(args.delay)

    (out_dir / "crawl_meta.json").write_text(
        json.dumps(meta_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n完成 {len(meta_list)} 页，元数据见 {out_dir / 'crawl_meta.json'}")


if __name__ == "__main__":
    main()
