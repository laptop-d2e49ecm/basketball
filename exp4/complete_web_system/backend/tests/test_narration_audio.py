import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import tts
from app.api import tasks


def _fake_edge_tts(monkeypatch, payload: bytes = b"ID3-audio"):
    """注入假 edge_tts 模块，记录每次合成的文本与韵律参数，避免测试联网。"""
    calls: list[dict[str, str]] = []

    class FakeCommunicate:
        def __init__(self, text: str, voice: str, rate: str, pitch: str):
            calls.append({"text": text, "voice": voice, "rate": rate, "pitch": pitch})

        async def stream(self):
            yield {"type": "audio", "data": payload}

    module = types.ModuleType("edge_tts")
    module.Communicate = FakeCommunicate
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    return calls


def _write_narration(task_dir: Path, status: str = "ready") -> Path:
    narration = task_dir / "narration.json"
    narration.write_text(
        json.dumps({"status": status, "text": "疑似传球，随后三分出手。", "sections": [{"text": "疑似传球。"}, {"text": "随后三分出手。"}]}),
        encoding="utf-8",
    )
    return narration


def test_synthesize_uses_sections_and_reuses_cache(tmp_path: Path, monkeypatch):
    narration = _write_narration(tmp_path)
    calls = _fake_edge_tts(monkeypatch)

    audio = tts.synthesize_narration(narration)
    assert audio.read_bytes() == b"ID3-audio"
    assert len(calls) == 1  # 无感叹号 → 全场一个平铺块
    assert "疑似传球" in calls[0]["text"] and "三分出手" in calls[0]["text"]
    assert calls[0]["voice"] == tts.DEFAULT_VOICE

    audio.write_bytes(b"ID3-audio-v2")  # 破坏缓存内容不应触发重合成（mtime 未变）
    audio.touch()  # 显式让 mp3 比 narration 新
    cached = tts.synthesize_narration(narration)
    assert cached.read_bytes() == b"ID3-audio-v2"


def test_synthesize_regenerates_when_narration_updated(tmp_path: Path, monkeypatch):
    narration = _write_narration(tmp_path)
    _fake_edge_tts(monkeypatch, payload=b"old")
    tts.synthesize_narration(narration)

    import os

    future = narration.stat().st_mtime + 10
    os.utime(narration, (future, future))
    _fake_edge_tts(monkeypatch, payload=b"new")
    assert tts.synthesize_narration(narration).read_bytes() == b"new"


def test_synthesize_applies_climax_prosody(tmp_path: Path, monkeypatch):
    """「！」高潮句加速抬调，平铺句用基础韵律；相邻同风格句子合并成一块。"""
    narration = tmp_path / "narration.json"
    narration.write_text(
        json.dumps(
            {
                "status": "ready",
                "text": "",
                "sections": [
                    {"text": "双方拉开阵型。"},
                    {"text": "外线果断出手！球进了！"},
                    {"text": "现场气氛沸腾。"},
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = _fake_edge_tts(monkeypatch, payload=b"chunk")

    audio = tts.synthesize_narration(narration)
    assert audio.read_bytes() == b"chunkchunkchunk"
    assert [c["rate"] for c in calls] == [tts.DEFAULT_RATE, tts.DEFAULT_CLIMAX_RATE, tts.DEFAULT_RATE]
    assert calls[0]["pitch"] == "+0Hz"
    assert calls[1]["pitch"] == tts.DEFAULT_CLIMAX_PITCH
    assert calls[1]["text"] == "外线果断出手！球进了！"


def test_audio_endpoint_serves_file_and_maps_errors(tmp_path: Path, monkeypatch):
    task_dir = tmp_path / "task123"
    task_dir.mkdir()
    _write_narration(task_dir)
    monkeypatch.setattr(tasks, "settings", SimpleNamespace(runs_dir=tmp_path))
    monkeypatch.setattr(tasks.task_repo, "get_task", lambda _: {"status": "ready"})
    _fake_edge_tts(monkeypatch, payload=b"mp3bytes")

    response = tasks.get_narration_audio("task123")
    assert response.path == task_dir / "narration.mp3"
    assert response.media_type == "audio/mpeg"

    narration = task_dir / "narration.json"
    narration.write_text(json.dumps({"status": "failed", "text": "", "sections": []}), encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        tasks.get_narration_audio("task123")
    assert exc.value.status_code == 409

    _write_narration(task_dir)  # ready 但合成失败（如网络）→ 503
    monkeypatch.setattr("app.tts.synthesize_narration", lambda _: (_ for _ in ()).throw(RuntimeError("语音合成返回空音频")))
    with pytest.raises(HTTPException) as exc:
        tasks.get_narration_audio("task123")
    assert exc.value.status_code == 503
    assert "空音频" in exc.value.detail
