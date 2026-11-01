# -*- coding: utf-8 -*-
"""任务 1.1.1（视觉数据获取）：从 HuggingFace 官方镜像下载 SportsMOT。

背景：SportsMOT 原始渠道（GitHub Google Form 申请 / OpenDataLab）审批周期不定；
官方作者组已将数据集上传至 HuggingFace（MCG-NJU/SportsMOT，CC BY-NC 4.0，非门控），
国内可经 hf-mirror.com 镜像直接下载，无需等待审批。

仓库结构：
    dataset/train.tar   6.24 GiB（含 gt 标注）
    dataset/val.tar     6.14 GiB（含 gt 标注）
    dataset/test.tar   21.6 GiB（无 gt，默认不下载）
    splits_txt/         各运动类别与官方划分的序列名列表

网络说明：若本机 DNS 被 Clash 等 TUN 工具劫持（域名解析到 198.18.0.0/15 fake-ip），
直连 hf-mirror 会失败；脚本检测到该情况时自动用 `curl --resolve` 钉住 hf-mirror
真实 IP 绕过劫持（可经 --hf-ip 覆盖）。

用法：
    python download_sportsmot_hf.py                    # 下载 train.tar + val.tar + splits
    python download_sportsmot_hf.py --parts val        # 只下 val
    python download_sportsmot_hf.py --list-only        # 只查看远端文件清单
"""
import argparse
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath

MIRROR = "https://hf-mirror.com"
REPO = "MCG-NJU/SportsMOT"
REAL_IP = "160.16.86.14"  # hf-mirror.com 真实 IP（绕过 fake-ip 劫持时钉住）
FAKE_IP_PREFIX = "198.18."  # Clash fake-ip 网段

# 远端文件：路径 -> 字节数（2026-09 从 HF API 读取；--list-only 可实时核对）
REMOTE_FILES = {
    "dataset/train.tar": 6703191552,
    "dataset/val.tar": 6592876544,
    "dataset/test.tar": 23208035328,
    "splits_txt/basketball.txt": None,
    "splits_txt/football.txt": None,
    "splits_txt/volleyball.txt": None,
    "splits_txt/train.txt": None,
    "splits_txt/val.txt": None,
    "splits_txt/test.txt": None,
}


def dns_hijacked(host: str) -> bool:
    """检测域名是否被解析到 fake-ip 网段（Clash TUN 接管 DNS 的特征）。"""
    import socket
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return any(i[4][0].startswith(FAKE_IP_PREFIX) for i in infos)


def curl_base_args(hf_ip: str) -> list:
    args = ["curl", "-sSL", "--fail", "--retry", "3", "--max-time", "600"]
    if hf_ip:
        args += ["--resolve", f"hf-mirror.com:443:{hf_ip}"]
    return args


def remote_size(path: str, hf_ip: str) -> int | None:
    """经 tree API 取远端文件大小；失败返回 None（用本地记录值兜底）。"""
    import json
    parent = str(PurePosixPath(path).parent)
    api = f"{MIRROR}/api/datasets/{REPO}/tree/main/{parent}"
    cmd = curl_base_args(hf_ip) + [api]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
        for item in json.loads(out):
            if item.get("path") == path:
                return item.get("size")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError, ValueError):
        pass
    return None


def download_chunk(url: str, out_path: Path, start: int, end: int, hf_ip: str) -> Path:
    """下载单个分段（HTTP Range），成功返回路径。"""
    tmp = out_path.with_suffix(".tmp")
    cmd = curl_base_args(hf_ip) + ["-r", f"{start}-{end}", "-o", str(tmp), url]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"curl 退出码 {r.returncode}: {url} [{start}-{end}]")
    if tmp.stat().st_size != end - start + 1:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"分段大小不符: 期望 {end - start + 1}, 实得 {tmp.stat().st_size}")
    tmp.replace(out_path)
    return out_path


def download_file(remote_path: str, out_file: Path, expected: int | None,
                  hf_ip: str, chunk_mb: int, workers: int) -> None:
    """分段并行下载一个远端文件到 out_file（parts/ 存分段，可断点续传）。"""
    if out_file.exists() and (expected is None or out_file.stat().st_size == expected):
        print(f"[SKIP] 已存在且大小一致: {out_file}")
        return
    expected = expected or remote_size(remote_path, hf_ip)
    if not expected:
        raise SystemExit(f"[!] 无法确定 {remote_path} 的大小，先跑 --list-only 核对")

    url = f"{MIRROR}/datasets/{REPO}/resolve/main/{remote_path}"
    parts_dir = out_file.parent / (out_file.name + ".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    chunk = chunk_mb * 1024 * 1024
    jobs, done = [], 0
    for s in range(0, expected, chunk):
        e = min(s + chunk, expected) - 1
        jobs.append((s, e, parts_dir / f"{s:012d}.part"))

    # 断点续传：跳过已完成的分段
    todo = [(s, e, p) for s, e, p in jobs
            if not (p.exists() and p.stat().st_size == e - s + 1)]

    print(f"[DL] {remote_path}: {expected / 1e9:.2f} GB，{len(todo)}/{len(jobs)} 个分段待下载")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(download_chunk, url, p, s, e, hf_ip): (s, e, p) for s, e, p in todo}
        for fut in as_completed(futs):
            s, e, p = futs[fut]
            try:
                fut.result()
                done += 1
                print(f"    [{done}/{len(todo)}] 分段 {s >> 20}-{e >> 20} MB 完成", flush=True)
            except Exception as exc:  # noqa: BLE001 —— 单段失败不终止整体，最后统一补漏
                print(f"    [RETRY-LATER] {p.name}: {exc}", flush=True)

    import time
    for attempt in range(3):  # 串行补漏重试：应对中途被 RST 阻断的情况
        missing = [(s, e, p) for s, e, p in jobs
                   if not (p.exists() and p.stat().st_size == e - s + 1)]
        if not missing:
            break
        print(f"[FIX] 第 {attempt + 1} 轮补漏，缺 {len(missing)} 段", flush=True)
        progressed = False
        for s, e, p in missing:
            try:
                download_chunk(url, p, s, e, hf_ip)
                print(f"    [FIX] 补齐分段 {p.name}", flush=True)
                progressed = True
            except Exception as exc:  # noqa: BLE001
                print(f"    [STILL-MISSING] {p.name}: {exc}", flush=True)
                break  # 连接仍被重置时不空转，等 60s 进下一轮
        if not progressed:
            time.sleep(60)
    missing = [(s, e, p) for s, e, p in jobs
               if not (p.exists() and p.stat().st_size == e - s + 1)]
    if missing:
        raise SystemExit(f"[!] 仍有 {len(missing)} 段未完成（连接可能被临时阻断），稍后重跑本脚本即可断点续传")

    print(f"[CAT] 拼接 {len(jobs)} 个分段 -> {out_file}")
    with out_file.open("wb") as w:
        for _, _, p in jobs:
            with p.open("rb") as r:
                shutil.copyfileobj(r, w)
    if out_file.stat().st_size != expected:
        out_file.unlink(missing_ok=True)
        raise SystemExit(f"[!] 拼接后大小不符: {out_file}")
    shutil.rmtree(parts_dir)
    print(f"[OK] {out_file} ({expected / 1e9:.2f} GB)")


def download_small(remote_path: str, out_file: Path, hf_ip: str) -> None:
    url = f"{MIRROR}/datasets/{REPO}/resolve/main/{remote_path}"
    r = subprocess.run(curl_base_args(hf_ip) + ["-o", str(out_file), url], capture_output=True)
    if r.returncode != 0 or not out_file.exists():
        raise SystemExit(f"[!] 下载失败: {remote_path}")


def main():
    parser = argparse.ArgumentParser(description="从 hf-mirror 下载 SportsMOT（官方 HF 镜像）")
    parser.add_argument("--out-dir", default="data/raw/sportsmot_hf", help="下载输出目录")
    parser.add_argument("--parts", default="train,val", help="要下载的 tar（可选 train/val/test）")
    parser.add_argument("--chunk-mb", type=int, default=64, help="分段大小（MB）")
    parser.add_argument("--workers", type=int, default=8, help="并行连接数")
    parser.add_argument("--hf-ip", default=REAL_IP, help="hf-mirror 真实 IP（钉住以绕过 DNS 劫持）")
    parser.add_argument("--list-only", action="store_true", help="只打印远端文件大小")
    args = parser.parse_args()

    if dns_hijacked("hf-mirror.com"):
        print(f"[NET] 检测到 fake-ip DNS 劫持，使用 --resolve 钉住 {args.hf_ip}")
    else:
        print("[NET] DNS 正常，直连 hf-mirror")

    if args.list_only:
        for p, sz in REMOTE_FILES.items():
            live = remote_size(p, args.hf_ip)
            flag = "" if live == sz else f"  (本地记录 {sz}, 远端 {live})"
            print(f"{p:32} {live if live is not None else '?'}{flag}")
        return

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = [x.strip() for x in args.parts.split(",") if x.strip()]

    for name in wanted:  # 大文件分段下载
        path = f"dataset/{name}.tar"
        download_file(path, out_dir / f"{name}.tar", REMOTE_FILES.get(path),
                      args.hf_ip, args.chunk_mb, args.workers)

    split_dir = out_dir / "splits_txt"  # 划分文件（含 basketball.txt）
    split_dir.mkdir(exist_ok=True)
    for f in ("basketball.txt", "train.txt", "val.txt"):
        download_small(f"splits_txt/{f}", split_dir / f, args.hf_ip)
    print(f"\n完成。tar 与 splits_txt 在 {out_dir}，下一步运行 extract_basketball.py 提取篮球序列")


if __name__ == "__main__":
    main()
