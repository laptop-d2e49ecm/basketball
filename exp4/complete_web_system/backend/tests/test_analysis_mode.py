import json
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from worker import video_service
from app.api import tasks


@pytest.mark.parametrize("mode,stride,expected", [("fast", 3, 10), ("detailed", 2, 15)])
def test_pipeline_sampling_preserves_timestamps_and_reports_stage_timings(tmp_path, monkeypatch, mode, stride, expected):
    source = tmp_path / "source.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 25, (64, 48))
    if not writer.isOpened(): pytest.skip("MP4 encoder unavailable")
    for _ in range(30): writer.write(np.zeros((48, 64, 3), dtype=np.uint8))
    writer.release()
    monkeypatch.setattr(video_service, "settings", SimpleNamespace(
        runs_dir=tmp_path, video_frame_step=2, inference_device="cpu", image_size=640,
        action_recognition_enabled=False, commentary_backend="stub", commentary_batch_size=5))
    stages = []
    metadata = {}
    monkeypatch.setattr(video_service.task_repo, "update_task", lambda _, **values: stages.append(values))
    monkeypatch.setattr(video_service.task_repo, "update_task_metadata", lambda _, **values: metadata.update(values))
    monkeypatch.setattr(video_service.task_repo, "expected_analysis_seconds", lambda _: 1)
    monkeypatch.setattr(video_service.task_repo, "notify_task", lambda *args: None)
    monkeypatch.setattr("worker.narration_service.run_task_narration", lambda *args: {"status": "ready"})
    class Model:
        def track(self, **kwargs):
            assert kwargs["vid_stride"] == stride
            assert kwargs["imgsz"] == 640
            for _ in range(expected):
                yield SimpleNamespace(orig_shape=(48, 64), boxes=None, speed={"inference": 1})
    video_service.process_task({"id": "task-one", "video_path": str(source), "metadata": {"frame_step": 2, "analysis_mode": mode}}, Model())
    rows = [json.loads(line) for line in (tmp_path / "task-one/detections.jsonl").read_text().splitlines()]
    assert len(rows) == expected
    assert rows[-1]["frame_idx"] == 29
    assert rows[-1]["t_ms"] == 1160
    assert metadata["frame_step"] == stride
    for key in ["detection_seconds", "action_seconds", "commentary_seconds", "narration_seconds"]:
        assert metadata[key] >= 0
    progresses = [item["progress"] for item in stages if "progress" in item]
    assert progresses == sorted(progresses)
    assert next(item["progress"] for item in stages if item.get("stage") == "narrating") == .9
    assert stages[-1]["status"] == "ready"


def test_upload_mode_is_validated_and_persisted(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.errors import register_exception_handlers
    monkeypatch.setattr(tasks, "settings", SimpleNamespace(runs_dir=tmp_path, max_upload_bytes=100, video_frame_step=2, task_backend="worker"))
    saved = []
    monkeypatch.setattr(tasks.task_repo, "create_task", lambda **values: saved.append(values))
    monkeypatch.setattr(tasks, "start_preview_generation", lambda _: None)
    app = FastAPI(); app.include_router(tasks.router); register_exception_handlers(app)
    with TestClient(app) as client:
        for data in [{}, {"analysis_mode": "detailed"}]:
            assert client.post("/api/v1/tasks", data=data, files={"file": ("game.mp4", b"video", "video/mp4")}).status_code == 202
        assert [row["metadata"]["analysis_mode"] for row in saved] == ["fast", "detailed"]
        assert client.post("/api/v1/tasks", data={"analysis_mode": "invalid"}, files={"file": ("game.mp4", b"video", "video/mp4")}).status_code == 400
