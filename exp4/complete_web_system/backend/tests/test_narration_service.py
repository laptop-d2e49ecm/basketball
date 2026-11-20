import json
import re
from pathlib import Path
from types import SimpleNamespace

from worker.narration_service import generate_narration, run_task_narration


class FakeAgent:
    def __init__(self):
        self.calls = []

    def invoke(self, payload):
        prompt = payload["messages"][0]["content"]
        offset = int(re.search(r"offset=(\d+)", prompt).group(1))
        limit = int(re.search(r"limit=(\d+)", prompt).group(1))
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
    assert len(agent.calls) == len(result["sections"]) == 4
    assert result["text"] == "\n\n".join(f"第 {n} 段解说" for n in range(1, 5))
    assert [call["args"]["offset"] for call in result["tool_calls"]] == [0, 6, 12, 18]
    assert sum(section["event_count"] for section in result["sections"]) == 21


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


def test_uniform_mp3_settings_and_cache(tmp_path, monkeypatch):
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
    assert audio.read_bytes() == b"part"
    assert calls == [("+10%", "+0Hz")]
    synthesize_narration(path)
    assert len(calls) == 1
    monkeypatch.setenv("BASKETBALL_TTS_CLIMAX_RATE", "+28%")
    monkeypatch.setenv("BASKETBALL_TTS_CLIMAX_PITCH", "+40Hz")
    synthesize_narration(path)
    assert len(calls) == 1
    monkeypatch.setenv("BASKETBALL_TTS_RATE", "+12%")
    synthesize_narration(path)
    assert calls[-1] == ("+12%", "+0Hz")


def test_narration_budget_covers_video_tail_and_contiguous_intervals(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps({"t_ms": 3000 + n * 1000, "type": "action"}) + "\n" for n in range(21)), encoding="utf-8")
    agent = FakeAgent()
    result = generate_narration("task123", path, agent_factory=lambda: agent,
                                context={"video_duration_seconds": 60})
    first, last = result["sections"][0], result["sections"][-1]
    assert first["start_ms"] == 0
    assert all(a["end_ms"] == b["start_ms"] for a, b in zip(result["sections"], result["sections"][1:]))
    assert last["end_ms"] == 60000
    target = round((60000 - last["start_ms"]) / 1000 * 5.5)
    assert f"约 {target} 个汉字" in agent.calls[-1]
    assert "现场解说" in agent.calls[0]
    assert "一至两句" not in agent.calls[0]


def test_track_number_cannot_be_spoken_as_jersey_number():
    from worker.commentary.evidence import unsupported
    assert "161号" in unsupported("白衣161号传球。", [{"track_id": 161}], None)
    assert not unsupported("白衣26号传球。", [{"scene": "白衣26号持球。"}], None)


def test_sparse_fast_events_still_produce_time_based_commentary(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps({"t_ms": n * 750, "type": "action"}) + "\n" for n in range(48)), encoding="utf-8")
    result = generate_narration("task123", path, agent_factory=FakeAgent, context={"video_duration_seconds": 36})
    assert len(result["sections"]) == 6
    assert sum(section["event_count"] for section in result["sections"]) == 48
    assert [section["start_ms"] for section in result["sections"]] == [0, 6000, 12000, 18000, 24000, 30000]


def test_long_narration_is_shortened_at_a_complete_clause():
    from worker.narration_service import _fit_spoken_length
    text = "球员把球传出去了。接球人继续运球，随后又将球送向另一侧。场上有人移动，队友继续接应。"
    result = _fit_spoken_length(text, 20)
    assert result == "球员把球传出去了。接球人继续运球。"
    assert _fit_spoken_length("没有任何标点的较长正文" * 5, 10) == "没有任何标点的较长正文" * 5
