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


class OnceAgent:
    """每次调用都返回固定文本，并记录收到的提示词；用于断言'是否触发重写'。"""

    def __init__(self, text):
        self.text = text
        self.calls = 0
        self.prompts = []

    def invoke(self, payload):
        self.calls += 1
        self.prompts.append(payload["messages"][0]["content"])
        call = {"name": "query_video_events", "args": {"task_id": "task123", "offset": 0, "limit": 1}}
        return {"messages": [
            SimpleNamespace(type="ai", tool_calls=[call], content=""),
            SimpleNamespace(type="tool", content="任务 task123 的关键事件：\n[0.0s] action"),
            SimpleNamespace(type="ai", tool_calls=[], content=self.text),
        ]}


def test_scene_evidence_unlocks_scene_words(tmp_path: Path):
    """快修2：画面观察明确提到三分线外时，'外线'不再是禁词，一次通过不重写。"""
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        json.dumps({"t_ms": 0, "type": "action", "action_zh": "运球", "scene": "进攻方在三分线外运球"}) + "\n",
        encoding="utf-8",
    )
    agent = OnceAgent("外线运着球，节奏不乱。")
    result = generate_narration("task123", events_path, agent_factory=lambda: agent)
    assert agent.calls == 1
    assert result["status"] == "ready"
    assert result["text"] == "外线运着球，节奏不乱。"


def test_user_score_unlocks_score_words_and_injects_prompt(tmp_path: Path):
    """快修1：用户填了比分时'领先'解禁，且对阵与比分注入提示词。"""
    events_path = tmp_path / "events.jsonl"
    events_path.write_text('{"t_ms":0,"type":"action","action_zh":"传球"}\n', encoding="utf-8")
    agent = OnceAgent("湖人 10 比 8 领先勇士。")
    result = generate_narration(
        "task123", events_path, agent_factory=lambda: agent,
        context={"team1": "湖人", "team2": "勇士", "score1": "10", "score2": "8"},
    )
    assert agent.calls == 1  # '领先'已解禁，没有触发重写
    assert result["text"] == "湖人 10 比 8 领先勇士。"
    assert "主队湖人" in agent.prompts[0] and "比分 10:8" in agent.prompts[0]


def test_persistent_ban_sanitizes_instead_of_failing(tmp_path: Path):
    """快修2：两稿都含无证据禁词时按句剔除兜底，整篇解说不再失败。"""
    events_path = tmp_path / "events.jsonl"
    events_path.write_text('{"t_ms":0,"type":"action","action_zh":"运球"}\n', encoding="utf-8")
    agent = OnceAgent("外线出手了。球员在跑位。")  # 事件无画面观察，'外线'始终无证据
    result = generate_narration("task123", events_path, agent_factory=lambda: agent)
    assert agent.calls == 2  # 重写一次
    assert result["status"] == "ready"  # 兜底后整篇不失败
    assert "外线" not in result["text"] and result["text"] == "球员在跑位。"


def test_run_task_narration_passes_metadata_context(tmp_path: Path, monkeypatch):
    """快修1：run_task_narration 从任务元数据取对阵/比分传给生成器；读不到时回退空。"""
    events_path = tmp_path / "events.jsonl"
    events_path.write_text('{"t_ms":0,"type":"action"}\n', encoding="utf-8")
    monkeypatch.setattr("app.db.task_repo.get_task", lambda tid: {"metadata": {"team1": "湖人"}})
    captured = {}

    def fake_generate(task_id, path, *, context=None, **kwargs):
        captured["context"] = context
        return {"task_id": task_id, "status": "ready", "text": "ok", "sections": []}

    monkeypatch.setattr("worker.narration_service.generate_narration", fake_generate)
    run_task_narration("task123", events_path)
    assert captured["context"] == {"team1": "湖人"}

    monkeypatch.setattr("app.db.task_repo.get_task", lambda tid: None)
    run_task_narration("task123", events_path)
    assert captured["context"] == {}


def test_narration_extracts_text_from_block_content(tmp_path: Path):
    """新中转最终消息 content 为块列表（reasoning+text）时，整场解说只取 text 块。"""
    events_path = tmp_path / "events.jsonl"
    events_path.write_text('{"t_ms":0,"type":"action"}\n', encoding="utf-8")

    class BlocksAgent(OnceAgent):
        def invoke(self, payload):
            self.calls += 1
            call = {"name": "query_video_events", "args": {"task_id": "task123", "offset": 0, "limit": 1}}
            return {"messages": [
                SimpleNamespace(type="ai", tool_calls=[call], content=""),
                SimpleNamespace(type="tool", content="任务 task123 的关键事件：\n[0.0s] action"),
                SimpleNamespace(type="ai", tool_calls=[], content=[
                    {"type": "reasoning", "encrypted_content": "gAAAAAB_should_not_leak"},
                    {"type": "text", "text": "球员疑似传球。"},
                ]),
            ]}

    result = generate_narration("task123", events_path, agent_factory=lambda: BlocksAgent("x"))
    assert result["status"] == "ready"
    assert result["text"] == "球员疑似传球。"
