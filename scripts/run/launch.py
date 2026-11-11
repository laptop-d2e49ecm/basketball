# -*- coding: utf-8 -*-
"""启动辅助：等待服务就绪、检查端口、查询健康状态。

被 start_exp5.bat / stop_exp5.bat 调用，也可手动使用：
    python scripts/run/launch.py wait http://127.0.0.1:8000/api/v1/health 90
    python scripts/run/launch.py port 8000
    python scripts/run/launch.py health
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request


def wait(url: str, timeout: float = 90.0) -> int:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if resp.status == 200:
                    print(f"[ready] {url}")
                    return 0
        except Exception as exc:  # noqa: BLE001
            last = type(exc).__name__
        time.sleep(1.0)
    print(f"[timeout] {url} ({last})")
    return 1


def port_free(port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        busy = s.connect_ex(("127.0.0.1", port)) == 0
    if busy:
        print(f"[busy] 端口 {port} 已被占用")
        return 1
    print(f"[free] 端口 {port}")
    return 0


def health() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=10) as resp:
            data = json.loads(resp.read())["result"]
    except Exception as exc:  # noqa: BLE001
        print(f"[fail] 健康检查不可用：{exc}")
        return 1
    print(json.dumps(data, ensure_ascii=False))
    ok = bool(data.get("detector_loaded")) and bool(data.get("text_clf_loaded"))
    print("[ok] 两个模型均已加载" if ok else "[warn] 有模型未加载，检查 weights/ 与 app/ml/")
    return 0 if ok else 2


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "wait":
        return wait(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 90.0)
    if cmd == "port":
        return port_free(int(sys.argv[2]))
    if cmd == "health":
        return health()
    print(f"未知命令：{cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
