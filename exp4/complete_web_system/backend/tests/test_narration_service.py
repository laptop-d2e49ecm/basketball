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


def test_score_and_scene_evidence():
    from worker.commentary.evidence import user_facts, unsupported, sanitize

    context = {"team1": "红队", "team2": "蓝队", "score1": 0, "score2": 2}
    assert "比分 0:2" in user_facts(context)
    assert "比分" not in user_facts({"team1": "红队", "score1": 0})
    text = "用户填写的比分为0:2。画面中球员位于篮下。球员三分命中！比分变成3:2。"
    terms = unsupported(text, [{"scene": "球员站在篮下。"}], context)
    assert sanitize(text, tuple(terms)) == "用户填写的比分为0:2。画面中球员位于篮下。"
    assert "篮下" in unsupported("球员在篮下。", [], None)


def test_dynamic_mp3_settings_and_cache(tmp_path, monkeypatch):
    import sys
    from app.tts import synthesize_narration

    calls = []

    class Voice:
        def __init__(self, text, voice, rate, pitch, **options):
            calls.append((rate, pitch))

        async def stream(self):
            yield {"type": "audio", "data": b"part"}

    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Voice))
    for key in ("RATE", "CLIMAX_RATE", "CLIMAX_PITCH"):
        monkeypatch.delenv("BASKETBALL_TTS_" + key, raising=False)
    path = tmp_path / "narration.json"
    path.write_text(json.dumps({"text": "双方落位。精彩的封盖！"}), encoding="utf-8")
    audio = synthesize_narration(path)
    assert audio.read_bytes() == b"partpart"
    assert calls == [("+10%", "+0Hz"), ("+35%", "+25Hz")]
    synthesize_narration(path)
    assert len(calls) == 2
    monkeypatch.setenv("BASKETBALL_TTS_CLIMAX_RATE", "+28%")
    synthesize_narration(path)
    assert calls[-1] == ("+28%", "+25Hz")


def test_narration_budget_covers_video_tail_and_contiguous_intervals(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps({"t_ms": 3000 + n * 1000, "type": "action"}) + "\n" for n in range(21)), encoding="utf-8")
    agent = FakeAgent()
    result = generate_narration("task123", path, agent_factory=lambda: agent,
                                context={"video_duration_seconds": 60})
    first, last = result["sections"]
    assert first["start_ms"] == 0
    assert first["end_ms"] == last["start_ms"] == 23000
    assert last["end_ms"] == 60000
    assert "约 204 个汉字" in agent.calls[1]
    assert "现场解说" in agent.calls[0]
    assert "一至两句" not in agent.calls[0]


def test_track_number_cannot_be_spoken_as_jersey_number():
    from worker.commentary.evidence import unsupported
    assert "161号" in unsupported("白衣161号传球。", [{"track_id": 161}], None)
    assert not unsupported("白衣26号传球。", [{"scene": "白衣26号持球。"}], None)
