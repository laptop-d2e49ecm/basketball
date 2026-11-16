import json
from pathlib import Path
from types import SimpleNamespace

from worker.narration_service import generate_narration, run_task_narration


class FakeAgent:
    def __init__(self):
        self.calls = []

    def invoke(self, payload):
        prompt = payload["messages"][0]["content"]
        offset = len(self.calls) * 20
        limit = 20 if offset == 0 else 1
        self.calls.append(prompt)
        call = {"name": "query_video_events", "args": {"task_id": "task123", "offset": offset, "limit": limit}}
        return {"messages": [
            SimpleNamespace(type="ai", tool_calls=[call], content=""),
            SimpleNamespace(type="tool", content="任务 task123 的关键事件：\n[0.0s] action"),
            SimpleNamespace(type="ai", tool_calls=[], content=f"第 {len(self.calls)} 段解说"),
        ]}


def test_agent_reads_all_event_pages_and_saves_narration(tmp_path: Path):
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("".join(json.dumps({"t_ms": n * 1000, "type": "action"}) + "\n" for n in range(21)), encoding="utf-8")
    agent = FakeAgent()
    result = generate_narration("task123", events_path, agent_factory=lambda: agent)
    assert result["status"] == "ready"
    assert result["event_count"] == 21
    assert len(agent.calls) == len(result["sections"]) == 2
    assert result["text"] == "第 1 段解说\n\n第 2 段解说"
    assert result["tool_calls"][1]["args"]["offset"] == 20


def test_narration_failure_is_saved_for_retry(tmp_path: Path, monkeypatch):
    events_path = tmp_path / "events.jsonl"
    events_path.write_text('{"t_ms": 0, "type": "action"}\n', encoding="utf-8")

    def fail(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("worker.narration_service.generate_narration", fail)
    result = run_task_narration("task123", events_path)
    saved = json.loads((tmp_path / "narration.json").read_text(encoding="utf-8"))
    assert result["status"] == saved["status"] == "failed"
    assert "model unavailable" not in saved["error"]


def test_narration_retries_unsupported_claim(tmp_path: Path):
    events_path = tmp_path / "events.jsonl"
    events_path.write_text('{"t_ms":0,"type":"action","action":"pass"}\n', encoding="utf-8")

    class RepairAgent:
        def __init__(self):
            self.count = 0

        def invoke(self, payload):
            self.count += 1
            call = {"name": "query_video_events", "args": {"task_id": "task123", "offset": 0, "limit": 1}}
            return {"messages": [
                SimpleNamespace(type="ai", tool_calls=[call], content=""),
                SimpleNamespace(type="tool", content="任务 task123 的关键事件：\n[0.0s] action pass"),
                SimpleNamespace(type="ai", tool_calls=[], content="教练示意后传球" if self.count == 1 else "球员疑似传球。"),
            ]}

    agent = RepairAgent()
    result = generate_narration("task123", events_path, agent_factory=lambda: agent)
    assert agent.count == 2
    assert result["text"] == "球员疑似传球。"
    assert len(result["tool_calls"]) == 2
