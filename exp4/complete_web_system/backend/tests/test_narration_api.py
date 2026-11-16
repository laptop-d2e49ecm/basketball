import json
from types import SimpleNamespace

from fastapi import BackgroundTasks

from app.api import tasks


def test_narration_endpoint_reads_task_file_and_retry(monkeypatch, tmp_path):
    task_dir = tmp_path / "task123"
    task_dir.mkdir()
    (task_dir / "events.jsonl").write_text('{"t_ms":0,"type":"action"}\n', encoding="utf-8")
    (task_dir / "narration.json").write_text(json.dumps({"task_id":"task123","status":"ready","text":"整场解说","sections":[]}), encoding="utf-8")
    monkeypatch.setattr(tasks, "settings", SimpleNamespace(runs_dir=tmp_path))
    monkeypatch.setattr(tasks.task_repo, "get_task", lambda _: {"status": "ready"})
    metadata = []
    monkeypatch.setattr(tasks.task_repo, "update_task_metadata", lambda *args, **kwargs: metadata.append((args, kwargs)))
    called = []
    def fake_narration(task_id, events):
        called.append((task_id, events))
        return {"status": "ready"}
    monkeypatch.setattr("worker.narration_service.run_task_narration", fake_narration)
    response = tasks.get_narration("task123")
    assert response.result["text"] == "整场解说"

    background = BackgroundTasks()
    response = tasks.retry_narration("task123", background)
    assert response.result["status"] == "running"
    assert len(background.tasks) == 1
    background.tasks[0].func(*background.tasks[0].args)
    assert called == [("task123", task_dir / "events.jsonl")]
    assert metadata[-1][1]["narration_status"] == "ready"
