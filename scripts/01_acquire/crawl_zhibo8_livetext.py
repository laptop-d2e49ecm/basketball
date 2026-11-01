# -*- coding: utf-8 -*-
"""爬取直播吧文字直播（解说语料，采集线②主案）。

数据链路（2026-10-11 逆向确认，详见 docs/DATA_DERIVATION.md）：
    比赛页内联配置(p_saishi_id/txt_live)
      -> 轮询 https://dingshi4pc.qiumibao.com/livetext/data/cache/livetext/{saishi_id}/0/page_10/{sid}.htm
         （sid 为 10 的倍数，每页 ≤10 条 JSON，按 live_sid 排序）
    特性：已结束比赛的文字**完整保留**在缓存里，可批量补爬历史场次。

每条记录 33 字段，关键字段：live_time(时间戳) / user_chn(解说员) / live_text(解说文本)
/ home_score,visit_score(当时比分) / event(事件类型) / left,right(比赛时间)。

合规口径（与实验 1 一致）：
    - robots.txt 未限制（404）；每请求间隔 ≥1s + 课程 UA + Referer；仅公开页面数据；
    - 语料仅课程内部使用，不对外再分发；来源记录写入 crawl_meta.json。

用法：
    # 单场测试
    python crawl_zhibo8_livetext.py --saishi-ids 2123074
    # 批量（ID 列表文件，每行一个）
    python crawl_zhibo8_livetext.py --ids-file data/raw/texts/livetext/nba_ids.txt
    # 从首页 schedule+recordData 自动收集篮球场次 ID 并爬取
    python crawl_zhibo8_livetext.py --collect
"""
import argparse
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = "https://dingshi4pc.qiumibao.com/livetext/data/cache/livetext/{sid}/0/page_10/{page}.htm"
HOME = "https://www.zhibo8.com/"
UA = "BasketballCourseProject/1.0 (student data-engineering exercise; contact: course-team)"
OUT_DIR = Path("data/raw/texts/livetext")
SLEEP = 0.5  # 每页间隔（秒）；--sleep 可覆盖

# 直连：绕过系统代理（Clash 等会显著拖慢该 CDN，实测 curl 直连 0.5s/页）
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url: str, referer: str = HOME) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": referer,
        "Accept": "application/json, text/plain, */*",
    })
    with _OPENER.open(req, timeout=20) as r:
        return r.read()


def crawl_game(saishi_id: str) -> dict:
    """爬单场：从 page_10/10.htm 起按 10 递增翻页。终止三条件：空页/非200、
    整页全为已见 live_id（服务端对超界页码会夹取返回）、硬上限 200 页。"""
    entries, page = [], 10
    seen: set = set()
    for _ in range(200):
        url = BASE.format(sid=saishi_id, page=page)
        try:
            data = json.loads(fetch(url))
        except Exception:  # noqa: BLE001 —— 404/空页 = 到头了
            break
        if not isinstance(data, list) or not data:
            break
        new = [e for e in data if e.get("live_id") and e["live_id"] not in seen]
        if not new:
            break  # 整页重复 = 服务端夹取了末页，到头
        entries.extend(new)
        seen.update(e["live_id"] for e in new)
        if len(data) < 10:
            break
        page += 10
        time.sleep(SLEEP)
    entries.sort(key=lambda e: int(e.get("live_sid") or 0))

    out_file = OUT_DIR / f"{saishi_id}.jsonl"
    with out_file.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return {"saishi_id": saishi_id, "entries": len(entries), "file": str(out_file)}


def collect_ids_from_home() -> list[dict]:
    """从直播吧首页的 schedule + recordData 收集**篮球**场次 ID。

    直播吧的 NBA 与 CBA 比赛页都在 /zhibo/nba/ 路径下，按此过滤。"""
    html = fetch(HOME).decode("utf-8", errors="replace")
    ids: dict[str, str] = {}
    for var in ("schedule", "recordData"):
        m = re.search(rf"var {var} = \[(.*?)\];", html, re.S)
        if not m:
            continue
        try:
            arr = json.loads("[" + m.group(1) + "]")
        except json.JSONDecodeError:
            continue
        for mid in set(re.findall(r"/zhibo/nba/\d{4}/match(\d{5,})v\.htm",
                                  json.dumps(arr, ensure_ascii=False))):
            ids.setdefault(mid, var)
    return [{"saishi_id": k, "source": v} for k, v in sorted(ids.items())]


def main() -> None:
    global SLEEP
    ap = argparse.ArgumentParser()
    ap.add_argument("--saishi-ids", default="", help="逗号分隔的场次 ID")
    ap.add_argument("--ids-file", default="", help="ID 列表文件（每行 ID 或 id<TAB>标签）")
    ap.add_argument("--collect", action="store_true", help="自动从首页收集篮球场次 ID")
    ap.add_argument("--sleep", type=float, default=SLEEP, help="每页请求间隔（秒）")
    ap.add_argument("--workers", type=int, default=3, help="并发爬取的场次数")
    args = ap.parse_args()
    SLEEP = args.sleep

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets: list[str] = []
    if args.saishi_ids:
        targets += [x.strip() for x in args.saishi_ids.split(",") if x.strip()]
    if args.ids_file:
        for line in Path(args.ids_file).read_text(encoding="utf-8").splitlines():
            mid = line.split("\t")[0].strip()
            if mid.isdigit():
                targets.append(mid)
    if args.collect:
        found = collect_ids_from_home()
        print(f"[COLLECT] 首页收集到 {len(found)} 个场次 ID")
        (OUT_DIR / "collected_ids.json").write_text(
            json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
        targets += [f["saishi_id"] for f in found]

    targets = [t for t in dict.fromkeys(targets) if t.isdigit()]
    print(f"[PLAN] 共 {len(targets)} 场待爬（{args.workers} 并发, 每页 {SLEEP}s）-> {OUT_DIR}")

    def crawl_one(mid: str) -> dict:
        out_file = OUT_DIR / f"{mid}.jsonl"
        if out_file.exists() and out_file.stat().st_size > 0:
            n = sum(1 for _ in out_file.open(encoding="utf-8"))
            return {"saishi_id": mid, "entries": n, "file": str(out_file), "skip": True}
        stat = crawl_game(mid)
        time.sleep(SLEEP)
        return stat

    meta, done, empty, i = [], 0, 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(crawl_one, mid): mid for mid in targets}
        for fut in as_completed(futs):
            mid = futs[fut]
            i += 1
            try:
                stat = fut.result()
                meta.append(stat)
                if stat.get("skip"):
                    continue
                if stat["entries"]:
                    done += 1
                    print(f"  [{i}/{len(targets)}] {mid}: {stat['entries']} 条", flush=True)
                else:
                    empty += 1
            except Exception as exc:  # noqa: BLE001
                meta.append({"saishi_id": mid, "error": str(exc)})
                print(f"  [{i}/{len(targets)}] {mid}: 失败 {exc}", flush=True)

    (OUT_DIR / "crawl_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(m.get("entries", 0) for m in meta)
    print(f"\n[OK] 成功 {done} 场 / 空 {empty} 场，共 {total} 条解说，元数据见 crawl_meta.json")


if __name__ == "__main__":
    main()
