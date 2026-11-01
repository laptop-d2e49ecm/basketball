# -*- coding: utf-8 -*-
"""从 HuggingFace 官方站直连下载 MultiSports 篮球子集（门控仓库，需 token）。

与 SportsMOT 的下载脚本（download_sportsmot_hf.py）关键差异：
- MultiSports 仓库是**门控**的（CC BY-NC 4.0，网页端登录勾选同意后可下）；
- hf-mirror 镜像不转发门控仓库的 Authorization，必须直连 huggingface.co；
- 分段请求带上 Bearer token；重定向到 CDN 签名地址后不再需要认证。

token 来源（优先级）：--token 参数 > 环境变量 HF_TOKEN。
不要把 token 写进代码或配置文件；下载完成后可在 HF 设置页撤销。

用法：
    python download_multisports_hf.py --parts trainval          # 仅 train 379 段（15.55 GB）
    python download_multisports_hf.py --parts trainval,test     # 加 val 147 段（再 6.84 GB）
    python download_multisports_hf.py --list-only               # 查看远端大小
"""
import argparse
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE = "https://huggingface.co/datasets/MCG-NJU/MultiSports/resolve/main"
# 远端文件：逻辑名 -> (仓库路径, 记录的字节数；None 表示未知，运行时探测)
REMOTE_FILES = {
    "trainval": ("data/trainval/basketball.tar", 15_550_000_000),  # 树 API 显示 ~15.55 GB
    "test": ("data/test/basketball.tar", 6_840_000_000),           # 树 API 显示 ~6.84 GB
}


def session(token: str) -> requests.Session:
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {token}"
    s.headers["User-Agent"] = "basketball-course-project/1.0"
    return s


def remote_size(s: requests.Session, path: str) -> int:
    r = s.head(f"{BASE}/{path}", allow_redirects=True, timeout=60)
    r.raise_for_status()
    return int(r.headers["Content-Length"])


def download_chunk(s: requests.Session, url: str, part_file: Path, start: int, end: int) -> None:
    r = s.get(url, headers={"Range": f"bytes={start}-{end}"}, stream=True, timeout=600)
    if r.status_code not in (200, 206):
        raise RuntimeError(f"HTTP {r.status_code}")
    tmp = part_file.with_suffix(".tmp")
    with tmp.open("wb") as f:
        for data in r.iter_content(1 << 20):
            f.write(data)
    if tmp.stat().st_size != end - start + 1:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"分段大小不符: 期望 {end - start + 1}, 实得 {tmp.stat().st_size}")
    tmp.replace(part_file)


def download_file(s: requests.Session, url: str, out_file: Path, expected: int,
                  chunk_mb: int, workers: int) -> None:
    if out_file.exists() and out_file.stat().st_size == expected:
        print(f"[SKIP] 已存在且大小一致: {out_file}")
        return
    parts_dir = out_file.parent / (out_file.name + ".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    chunk = chunk_mb * 1024 * 1024
    jobs = [(st, min(st + chunk, expected) - 1, parts_dir / f"{st:012d}.part")
            for st in range(0, expected, chunk)]

    todo = [(st, en, p) for st, en, p in jobs
            if not (p.exists() and p.stat().st_size == en - st + 1)]
    print(f"[DL] {out_file.name}: {expected / 1e9:.2f} GB, {len(todo)}/{len(jobs)} 个分段待下载", flush=True)

    for attempt in range(5):
        if not todo:
            break
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(download_chunk, s, url, p, st, en): (st, en, p)
                    for st, en, p in todo}
            for fut in as_completed(futs):
                st, en, p = futs[fut]
                try:
                    fut.result()
                    done += 1
                    if done % 10 == 0 or done == len(todo):
                        print(f"    进度 {done}/{len(todo)}", flush=True)
                except Exception as exc:  # noqa: BLE001 —— 失败分段留给下一轮
                    print(f"    [RETRY-LATER] {p.name}: {exc}", flush=True)
        todo = [(st, en, p) for st, en, p in todo
                if not (p.exists() and p.stat().st_size == en - st + 1)]
        if todo:
            print(f"[FIX] 第 {attempt + 1} 轮补漏，缺 {len(todo)} 段，等 30s", flush=True)
            time.sleep(30)

    if todo:
        raise SystemExit(f"[!] 仍有 {len(todo)} 段未完成，重跑本脚本即可断点续传")

    print(f"[CAT] 拼接 {len(jobs)} 个分段 -> {out_file}", flush=True)
    with out_file.open("wb") as w:
        for _, _, p in jobs:
            with p.open("rb") as r:
                shutil.copyfileobj(r, w)
    if out_file.stat().st_size != expected:
        out_file.unlink(missing_ok=True)
        raise SystemExit(f"[!] 拼接后大小不符: {out_file}")
    shutil.rmtree(parts_dir)
    print(f"[OK] {out_file} ({expected / 1e9:.2f} GB)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="直连 HF 下载 MultiSports 篮球子集（门控，需 token）")
    parser.add_argument("--out-dir", default="data/raw/multisports", help="下载输出目录")
    parser.add_argument("--parts", default="trainval,test", help="要下载的 tar（trainval/test）")
    parser.add_argument("--token", default=os.environ.get("HF_TOKEN", ""), help="HF 访问令牌（或环境变量 HF_TOKEN）")
    parser.add_argument("--chunk-mb", type=int, default=64, help="分段大小（MB）")
    parser.add_argument("--workers", type=int, default=8, help="并行连接数")
    parser.add_argument("--list-only", action="store_true", help="只探测远端文件大小")
    parser.add_argument("--test-chunk", action="store_true", help="只下载 1 个分段验证连通性")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("[!] 缺少 token：用 --token 或环境变量 HF_TOKEN 提供（HF 设置页创建，Read 权限）")
    s = session(args.token)

    if args.list_only:
        for name, (path, _) in REMOTE_FILES.items():
            try:
                print(f"{name:10} {path:34} {remote_size(s, path):,} bytes")
            except Exception as exc:  # noqa: BLE001
                print(f"{name:10} {path:34} 探测失败: {exc}")
        return

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in [x.strip() for x in args.parts.split(",") if x.strip()]:
        path, recorded = REMOTE_FILES[name]
        expected = recorded
        try:
            live = remote_size(s, path)
            if recorded and abs(live - recorded) / recorded > 0.05:
                print(f"[WARN] {path} 远端大小 {live:,} 与记录 {recorded:,} 差异超过 5%，以远端为准")
            expected = live
        except Exception as exc:  # noqa: BLE001
            if recorded is None:
                raise SystemExit(f"[!] 无法确定 {path} 大小: {exc}")
            print(f"[WARN] 大小探测失败（{exc}），用记录值 {recorded:,}")

        url = f"{BASE}/{path}"
        out_file = out_dir / f"{name}.tar"
        if args.test_chunk:
            p = out_dir / "connectivity_test.part"
            download_chunk(s, url, p, 0, 1024 * 1024 - 1)
            print(f"[TEST-OK] {name} 首段 1MB 下载成功，Range 请求可用")
            p.unlink(missing_ok=True)
            continue
        download_file(s, url, out_file, expected, args.chunk_mb, args.workers)

    print("\n完成。tar 位于", out_dir)


if __name__ == "__main__":
    main()
