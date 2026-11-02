from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2

from app.core.config import settings
from app.core.coords import normalize_xyxy
from app.core.device import resolve_torch_device
from app.db import task_repo
from worker.commentary.stub import StubCommentaryService
from worker.event_service import iter_heuristic_events

logger = logging.getLogger("basketball-video-service")


def _write_jsonl_line(stream: Any, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, ensure_ascii=False) + "\n")


def process_task(task: dict[str, Any], model: Any) -> None:
    task_id = task["id"]
    task_dir = settings.runs_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    video_path = Path(task["video_path"])
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("无法打开视频，请确认文件是有效的 MP4 视频")

    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    frame_total_raw = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    requested_step = int(task.get("metadata", {}).get("frame_step", settings.video_frame_step))
    frame_step = max(1, requested_step)
    if frame_total_raw > 0:
        frame_step = min(frame_step, frame_total_raw)
        # Ultralytics' video loader reports floor(frame_count / vid_stride).
        frames_total = frame_total_raw // frame_step
    else:
        # Keep every frame when metadata cannot support reliable stride progress.
        frame_step = 1
        frames_total = None
    cap.release()
    task_repo.update_task_metadata(task_id, frame_step=frame_step)
    task_repo.update_task(
        task_id,
        stage="detecting",
        frames_total=frames_total,
        notify={
            "type": "progress",
            "stage": "detecting",
            "progress": 0,
            "frames_total": frames_total,
            "frame_step": frame_step,
        },
    )

    started = perf_counter()
    device = resolve_torch_device(settings.inference_device)
    logger.info("Using inference device %s for task %s", device, task_id)
    inference_seconds = 0.0
    frames_done = 0
    last_progress_notice = 0.0
    task_dir = settings.runs_dir / task_id
    detections_path = task_dir / "detections.jsonl"
    events_path = task_dir / "events.jsonl"
    with detections_path.open("w", encoding="utf-8") as detections_file:
        results_stream = iter(
            model.track(
                source=str(video_path),
                stream=True,
                persist=False,
                tracker="bytetrack.yaml",
                imgsz=settings.image_size,
                vid_stride=frame_step,
                device=device,
                verbose=False,
            )
        )
        while True:
            try:
                frame_started = perf_counter()
                result = next(results_stream)
                frame_elapsed = perf_counter() - frame_started
            except StopIteration:
                break

            frame_height, frame_width = result.orig_shape
            boxes = result.boxes
            frame_boxes: list[dict[str, Any]] = []
            if boxes is not None and len(boxes) > 0:
                xyxy = boxes.xyxy.cpu().tolist()
                confidences = boxes.conf.cpu().tolist()
                track_ids = boxes.id.int().cpu().tolist() if boxes.id is not None else [None] * len(xyxy)
                for coords, confidence, track_id in zip(xyxy, confidences, track_ids):
                    normalized = normalize_xyxy(coords, frame_width, frame_height)
                    if normalized is None:
                        continue
                    cx, cy, box_width, box_height = normalized
                    frame_boxes.append(
                        {
                            "cx": cx,
                            "cy": cy,
                            "w": box_width,
                            "h": box_height,
                            "conf": float(confidence),
                            "track_id": int(track_id) if track_id is not None else None,
                        }
                    )

            infer_ms = result.speed.get("inference") if result.speed else None
            inference_seconds += (float(infer_ms) / 1000) if infer_ms is not None else frame_elapsed
            # Ultralytics reads one frame after each stride-sized grab, so the
            # first analyzed frame is frame_step - 1 in the original video.
            frame_idx = (frames_done + 1) * frame_step - 1
            t_ms = round((frame_idx / fps) * 1000) if fps > 0 else 0
            _write_jsonl_line(
                detections_file,
                {
                    "frame_idx": frame_idx,
                    "t_ms": t_ms,
                    "image_w": frame_width,
                    "image_h": frame_height,
                    "boxes": frame_boxes,
                },
            )
            frames_done += 1

            progress = min(0.99, frames_done / frames_total) if frames_total else 0.0
            should_report = (
                frames_done % 25 == 0
                if frames_total is None
                else progress - last_progress_notice >= 0.01
            )
            if should_report:
                average_ms = (inference_seconds / frames_done) * 1000
                task_repo.update_task(
                    task_id,
                    frames_done=frames_done,
                    progress=progress,
                    avg_infer_ms=average_ms,
                    notify={
                        "type": "progress",
                        "stage": "detecting",
                        "progress": progress,
                        "frames_done": frames_done,
                        "frames_total": frames_total,
                        "frame_step": frame_step,
                    },
                )
                last_progress_notice = progress

    task_repo.update_task(
        task_id,
        stage="commentary",
        progress=0.99,
        frames_done=frames_done,
        notify={
            "type": "progress",
            "stage": "commentary",
            "progress": 0.99,
            "frames_done": frames_done,
            "frames_total": frames_total,
            "frame_step": frame_step,
        },
    )
    commentary_service = StubCommentaryService()
    with events_path.open("w", encoding="utf-8") as events_file:
        for event in iter_heuristic_events(detections_path):
            event["text"] = commentary_service.generate(event)
            _write_jsonl_line(events_file, event)
            task_repo.notify_task(
                task_id,
                {
                    "type": "commentary",
                    "t_ms": event["t_ms"],
                    "text": event["text"],
                    "event": event["type"],
                    "source": event["source"],
                },
            )

    total_seconds = perf_counter() - started
    average_ms = (inference_seconds / frames_done) * 1000 if frames_done else None
    finished_at = datetime.now(UTC).isoformat()
    task_repo.update_task(
        task_id,
        status="ready",
        stage="ready",
        progress=1,
        frames_done=frames_done,
        avg_infer_ms=average_ms,
        total_seconds=total_seconds,
        finished_at=finished_at,
        notify={
            "type": "done",
            "stats": {
                "frames_total": frames_done,
                "frame_step": frame_step,
                "avg_infer_ms": average_ms,
                "total_seconds": total_seconds,
            },
        },
    )
