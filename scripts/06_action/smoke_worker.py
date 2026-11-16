# -*- coding: utf-8 -*-
"""动作识别端到端冒烟：临时 DB + 临时 runs，跑完整 process_task 流水线。

用法（在仓库根目录）：
    .venv/Scripts/python scripts/06_action/smoke_worker.py [--conf 0.6]

用 backend/weights 的部署权重（2026-11-16 起为 Kaggle 正式训练产物）走
检测 → 动作识别 → 解说（stub）全链路；正式验收阈值 0.6。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "exp4/complete_web_system/backend"
SMOKE_DIR = ROOT / "models/exp5_action_smoke/e2e"

os.environ.setdefault("BASKETBALL_DB_PATH", str(SMOKE_DIR / "tasks.db"))
os.environ.setdefault("BASKETBALL_RUNS_DIR", str(SMOKE_DIR / "runs"))
os.environ.setdefault("BASKETBALL_ACTION", "on")
os.environ.setdefault("BASKETBALL_COMMENTARY", "stub")
os.environ.setdefault("BASKETBALL_VISION_CAPTIONS", "off")
os.environ.setdefault("BASKETBALL_DEVICE", "cpu")

sys.path.insert(0, str(BACKEND))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", type=float, default=0.6, help="生产阈值 0.6；演示嫌事件过密可试 0.7")
    ap.add_argument("--video", default=str(ROOT / "samples/demo_video.mp4"))
    args = ap.parse_args()
    os.environ["BASKETBALL_ACTION_CONF"] = str(args.conf)

    from ultralytics import YOLO

    from app.core.config import settings
    from app.db import task_repo
    from app.db.database import initialize_database
    from worker.video_service import process_task

    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()
    task_id = "smoke-action-e2e"
    task_repo.delete_task(task_id)
    task_repo.create_task(
        task_id=task_id,
        video_name="demo_video.mp4",
        video_path=args.video,
        metadata={"frame_step": settings.video_frame_step},
    )
    model = YOLO(str(settings.model_path))
    process_task(task_repo.get_task(task_id), model)

    task = task_repo.get_task(task_id)
    events_path = settings.runs_dir / task_id / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    action_events = [e for e in events if e["type"] == "action"]
    print(f"\n任务状态: {task['status']}  总耗时 {task['total_seconds']:.1f}s  事件 {len(events)} 条（动作 {len(action_events)}）")
    for e in action_events[:10]:
        print(f"  t={e['t_ms']/1000:6.1f}s  {e['action']:12s} conf={e['conf']:.2f}  {e['text']}")
    other = [e for e in events if e["type"] != "action"][:3]
    for e in other:
        print(f"  t={e['t_ms']/1000:6.1f}s  [{e['type']}] {e['text']}")


if __name__ == "__main__":
    main()
