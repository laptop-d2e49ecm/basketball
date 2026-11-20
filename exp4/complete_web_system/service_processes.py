"""Discover only services launched from this project, including Windows venv children."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parent


def service_kind(command, cwd, root=ROOT):
    backend, frontend = (root / "backend").resolve(), (root / "frontend").resolve()
    directory = Path(cwd).resolve()
    if "-m" in command:
        index = command.index("-m")
        module = command[index + 1] if index + 1 < len(command) else ""
        app_dir = None
        if "--app-dir" in command:
            position = command.index("--app-dir")
            if position + 1 < len(command):
                app_dir = Path(command[position + 1]).resolve()
        if module == "uvicorn" and "app.main:app" in command and (app_dir == backend or (app_dir is None and directory == backend)):
            return "api"
        if module == "worker.main" and directory == backend:
            return "worker"
    vite = (frontend / "node_modules/vite/bin/vite.js").resolve()
    if directory == frontend and any(Path(arg).resolve() == vite for arg in command[1:] if arg.endswith("vite.js")):
        return "frontend"
    return None


def inspect_process(process):
    try:
        kind = service_kind(process.cmdline(), process.cwd())
        if kind:
            return {"id": process.pid, "parent": process.ppid(), "service": kind, "started": process.create_time()}
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        pass
    return None


def discover():
    rows = [row for process in psutil.process_iter() if (row := inspect_process(process))]
    roots = []
    for row in rows:
        if any(parent["id"] == row["parent"] and parent["service"] == row["service"] for parent in rows):
            continue
        family = {row["id"]}
        while True:
            more = {item["id"] for item in rows if item["parent"] in family and item["service"] == row["service"]}
            if more <= family:
                break
            family |= more
        ports = set()
        for pid in family:
            try:
                ports.update(connection.laddr.port for connection in psutil.Process(pid).net_connections(kind="tcp") if connection.status == psutil.CONN_LISTEN)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        roots.append({**row, "ports": sorted(ports)})
    return roots


def stop(pid):
    try:
        parent = psutil.Process(pid)
        owner = inspect_process(parent)
        if not owner:
            raise RuntimeError("Refusing to stop a process outside this project")
        processes = parent.children(recursive=True)
        # Inspect every process again immediately before stopping it.
        for process in reversed(processes):
            row = inspect_process(process)
            if row and row["service"] == owner["service"]:
                process.terminate()
        if inspect_process(parent) == owner:
            parent.terminate()
        _, alive = psutil.wait_procs(processes + [parent], timeout=5)
        for process in alive:
            row = inspect_process(process)
            if row and row["service"] == owner["service"]:
                process.kill()
    except psutil.NoSuchProcess:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["list", "stop"])
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    if args.action == "list":
        print(json.dumps(discover()))
    else:
        if args.pid is None:
            parser.error("--pid is required")
        stop(args.pid)
