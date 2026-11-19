"""Verify video-bound chat history and real frame extraction for the workspace."""

from types import SimpleNamespace
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.api import agent, tasks
from app.db import agent_sessions, database


def test_sessions_are_grouped_by_video_and_restore_tool_history(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "settings", SimpleNamespace(database_path=tmp_path / "tasks.db"))
    monkeypatch.setattr(agent_sessions, "connection", database.connection)
    monkeypatch.setattr(agent_sessions, "_TABLE_READY", False)
    one = agent_sessions.new_session("video-one")
    two = agent_sessions.new_session("video-two")
    agent_sessions.append_history(one, [
        {"role": "user", "content": "这场比赛有什么关键事件？"},
        {"role": "agent", "content": "先看第 6 秒", "tool_calls": [{"tool": "query_video_events", "status": "ok"}]},
    ])
    assert [row["session_id"] for row in agent_sessions.list_sessions("video-one")] == [one]
    assert [row["session_id"] for row in agent_sessions.list_sessions("video-two")] == [two]
    assert agent_sessions.get_session(one)["history"][1]["tool_calls"][0]["tool"] == "query_video_events"
    assert agent_sessions.get_session("missing") is None


def test_frame_endpoint_uses_original_video_and_rejects_unready_task(monkeypatch, tmp_path):
    source = tmp_path / "game.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 2, (64, 48))
    if not writer.isOpened():
        pytest.skip("MP4 encoder unavailable")
    writer.write(np.full((48, 64, 3), (30, 90, 180), dtype=np.uint8))
    writer.write(np.full((48, 64, 3), (60, 120, 210), dtype=np.uint8))
    writer.release()
    state = {"status": "ready", "video_path": str(source)}
    monkeypatch.setattr(tasks.task_repo, "get_task", lambda _: state)
    response = tasks.get_task_frame("video-one", 0)
    frame = Path(response.path)
    assert frame.is_file()
    assert frame.read_bytes()[:2] == b"\xff\xd8"
    state["status"] = "running"
    with pytest.raises(Exception) as error:
        tasks.get_task_frame("video-one", 0)
    assert error.value.status_code == 409


def test_agent_chat_rejects_session_from_other_video(monkeypatch):
    monkeypatch.setattr(agent.task_repo, "get_task", lambda _: {"status": "ready"})
    monkeypatch.setattr(agent_sessions, "get_session", lambda _: {"task_id": "video-one", "history": []})
    with pytest.raises(Exception) as error:
        agent.agent_chat(agent.AgentChatRequest(session_id="sess_1", task_id="video-two", message="你好"), None)
    assert error.value.status_code == 409


def test_upload_creates_new_task_directory(monkeypatch, tmp_path):
    from io import BytesIO
    from fastapi import UploadFile
    monkeypatch.setattr(tasks, "settings", SimpleNamespace(
        runs_dir=tmp_path, max_upload_bytes=1000, video_frame_step=2, task_backend="local"))
    saved = []
    monkeypatch.setattr(tasks.task_repo, "create_task", lambda **kw: saved.append(kw))
    monkeypatch.setattr(tasks, "start_preview_generation", lambda _: None)
    result = tasks.create_task(file=UploadFile(filename="demo.mp4", file=BytesIO(b"video")),
                               video_name=None, team1=None, team2=None, score1=None, score2=None)
    task_id = result.result.task_id
    assert saved[0]["task_id"] == task_id
    assert Path(saved[0]["video_path"]) == tmp_path / task_id / "source.mp4"
    assert Path(saved[0]["video_path"]).read_bytes() == b"video"


def test_tool_trace_matches_parallel_results_by_call_id():
    calls = SimpleNamespace(type="ai", tool_calls=[
        {"id": "first", "name": "player_detect", "args": {"image_path": "frame.jpg"}},
        {"id": "second", "name": "commentary_classify", "args": {"text": "传球"}},
        {"id": "missing", "name": "retrieve_commentary", "args": {"query": "传球"}},
    ])
    trace = agent._trace_from_messages([
        calls,
        SimpleNamespace(type="tool", tool_call_id="second", content="工具调用失败：分类模型未就绪"),
        SimpleNamespace(type="tool", tool_call_id="first", content="检测到 8 名球员，推理耗时 12ms"),
    ])
    assert trace[0]["result_summary"].startswith("检测到 8 名球员")
    assert trace[0]["status"] == "ok"
    assert trace[0]["elapsed_ms"] == 12
    assert trace[1]["status"] == "error"
    assert trace[2]["status"] == "error"
    assert trace[2]["result_summary"] == "工具未返回结果"
