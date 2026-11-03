from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import cv2

logger = logging.getLogger("basketball-preview")
PreviewState = Literal["processing", "ready", "failed"]

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-preview")
_jobs: dict[Path, Future[None]] = {}
_jobs_lock = Lock()


def _state_path(task_dir: Path) -> Path:
    return task_dir / "preview-status.json"


def _write_state(task_dir: Path, value: dict[str, Any]) -> None:
    target = _state_path(task_dir)
    temporary = task_dir / "preview-status.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, target)


def _read_state(task_dir: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(_state_path(task_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("status") not in {"processing", "ready", "failed"}:
        return None
    return value


def _video_fourcc(source: Path) -> str:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError("OpenCV 无法读取上传的视频")
    raw_code = int(capture.get(cv2.CAP_PROP_FOURCC))
    capture.release()
    return "".join(chr((raw_code >> (8 * offset)) & 0xFF) for offset in range(4)).strip("\x00 ").upper()


def _convert_to_browser_mp4(source: Path, output: Path) -> None:
    import imageio_ffmpeg

    temporary = output.with_name("preview.transcoding.mp4")
    temporary.unlink(missing_ok=True)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-threads",
        "2",
        "-movflags",
        "+faststart",
        str(temporary),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("FFmpeg 没有生成有效的预览视频")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def _build_preview(task_dir: Path) -> None:
    source = task_dir / "source.mp4"
    output = task_dir / "preview.mp4"
    try:
        if not source.is_file():
            raise RuntimeError("找不到原始视频")

        fourcc = _video_fourcc(source)
        if fourcc in {"AVC1", "AVC3", "H264", "X264"}:
            filename = source.name
            converted = False
        else:
            _convert_to_browser_mp4(source, output)
            filename = output.name
            converted = True

        _write_state(
            task_dir,
            {"status": "ready", "filename": filename, "converted": converted, "error": None},
        )
        logger.info("Browser preview ready for %s (fourcc=%s, converted=%s)", task_dir.name, fourcc, converted)
    except Exception:
        logger.exception("Could not create browser preview for %s", task_dir.name)
        output.unlink(missing_ok=True)
        _write_state(
            task_dir,
            {
                "status": "failed",
                "filename": None,
                "converted": False,
                "error": "暂时无法生成浏览器预览，请确认视频有效并安装了项目依赖。",
            },
        )


def start_preview_generation(task_dir: Path) -> dict[str, Any]:
    """Ensure one background browser-preview job exists for a task."""
    task_dir = task_dir.resolve()
    with _jobs_lock:
        state = _read_state(task_dir)
        future = _jobs.get(task_dir)
        if future is not None and not future.done():
            return {"status": "processing", "converted": False, "error": None}
        if state and state.get("status") == "ready":
            filename = state.get("filename")
            if filename in {"source.mp4", "preview.mp4"} and (task_dir / filename).is_file():
                return state
        if state and state.get("status") == "failed":
            return state

        _write_state(
            task_dir,
            {"status": "processing", "filename": None, "converted": False, "error": None},
        )
        _jobs[task_dir] = _executor.submit(_build_preview, task_dir)
        return {"status": "processing", "converted": False, "error": None}


def get_preview_state(task_dir: Path) -> dict[str, Any]:
    return start_preview_generation(task_dir)


def get_preview_file(task_dir: Path) -> Path | None:
    state = _read_state(task_dir)
    if not state or state.get("status") != "ready":
        return None
    filename = state.get("filename")
    if filename not in {"source.mp4", "preview.mp4"}:
        return None
    path = task_dir / filename
    return path if path.is_file() else None


def remove_preview_task_data(task_dir: Path) -> None:
    """Remove preview data now, or after an active conversion releases its files."""
    task_dir = task_dir.resolve()
    with _jobs_lock:
        future = _jobs.get(task_dir)
        if future is None or future.done():
            _jobs.pop(task_dir, None)
            defer_cleanup = False
        else:
            defer_cleanup = True

            def cleanup_after_conversion(_: Future[None]) -> None:
                with _jobs_lock:
                    if _jobs.get(task_dir) is future:
                        _jobs.pop(task_dir, None)
                shutil.rmtree(task_dir, ignore_errors=True)

    if not defer_cleanup:
        shutil.rmtree(task_dir, ignore_errors=True)
    elif future is not None:
        future.add_done_callback(cleanup_after_conversion)
