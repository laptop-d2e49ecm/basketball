import json
import sys
import types
import math
import struct
import subprocess
import wave
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import tts
from app.api import tasks


def test_segment_trim_removes_edge_silence_and_preserves_spoken_audio():
    import imageio_ffmpeg

    rate = 24000
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        samples = [0] * (rate // 5)
        samples += [round(6000 * math.sin(index * 2 * math.pi * 440 / rate)) for index in range(rate)]
        samples += [0] * (rate * 4 // 5)
        output.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    encoded = subprocess.run([exe, '-loglevel', 'error', '-f', 'wav', '-i', 'pipe:0', '-f', 'mp3', 'pipe:1'],
        input=buffer.getvalue(), capture_output=True, check=True).stdout
    trimmed = tts._trim_segment_silence(encoded)
    decoded = subprocess.run([exe, '-loglevel', 'error', '-f', 'mp3', '-i', 'pipe:0', '-f', 's16le', 'pipe:1'],
        input=trimmed, capture_output=True, check=True).stdout
    seconds = len(decoded) / (rate * 2)
    assert 1 <= seconds < 1.3


def _fake_edge_tts(monkeypatch, payload: bytes = b"ID3-audio"):
    """注入假 edge_tts 模块，记录每次合成的文本与韵律参数，避免测试联网。"""
    calls: list[dict[str, str]] = []

    class FakeCommunicate:
        def __init__(self, text: str, voice: str, rate: str, pitch: str, **options):
            calls.append({"text": text, "voice": voice, "rate": rate, "pitch": pitch, **options})

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


def test_emphatic_segment_uses_one_voice_and_one_trim(tmp_path, monkeypatch):
    path = tmp_path / "narration.json"
    path.write_text(json.dumps({"sections": [{"text": "球先护住。往里一步！"}]}), encoding="utf-8")
    calls = _fake_edge_tts(monkeypatch, payload=b"raw-voice")
    trimmed = []

    def trim(data):
        trimmed.append(data)
        return b"trimmed"

    monkeypatch.setattr(tts, "_trim_segment_silence", trim)
    audio = tts.synthesize_narration(path, 0)
    assert len(calls) == 1
    assert trimmed == [b"raw-voice"]
    assert audio.read_bytes() == b"trimmed"
    tts.synthesize_narration(path, 0)
    assert len(calls) == 1


def test_synthesize_regenerates_when_narration_updated(tmp_path: Path, monkeypatch):
    narration = _write_narration(tmp_path)
    _fake_edge_tts(monkeypatch, payload=b"old")
    tts.synthesize_narration(narration)

    import os

    future = narration.stat().st_mtime + 10
    os.utime(narration, (future, future))
    _fake_edge_tts(monkeypatch, payload=b"new")
    assert tts.synthesize_narration(narration).read_bytes() == b"new"


def test_synthesize_keeps_same_voice_rate_and_pitch_for_exclamations(tmp_path: Path, monkeypatch):
    """Mixed punctuation must never select a second pitch or speaking rate."""
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
    assert audio.read_bytes() == b"chunk"
    assert len(calls) == 1
    assert calls[0]["voice"] == tts.DEFAULT_VOICE
    assert calls[0]["rate"] == tts.DEFAULT_RATE
    assert calls[0]["pitch"] == "+0Hz"
    assert "外线果断出手！球进了！" in calls[0]["text"]


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
    monkeypatch.setattr("app.tts.synthesize_narration", lambda *args: (_ for _ in ()).throw(RuntimeError("语音合成返回空音频")))
    with pytest.raises(HTTPException) as exc:
        tasks.get_narration_audio("task123")
    assert exc.value.status_code == 503
    assert "空音频" in exc.value.detail


def test_section_audio_uses_same_voice_and_rejects_invalid_section(tmp_path, monkeypatch):
    narration = _write_narration(tmp_path)
    calls = _fake_edge_tts(monkeypatch)
    audio = tts.synthesize_narration(narration, 1)
    assert audio.name == "narration-section-1.mp3"
    assert calls[0]["text"] == "随后三分出手。"
    assert calls[0]["rate"] == tts.DEFAULT_RATE
    with pytest.raises(ValueError, match="段落不存在"):
        tts.synthesize_narration(narration, 2)


def test_legacy_voice_cache_is_regenerated(tmp_path, monkeypatch):
    narration = _write_narration(tmp_path)
    _fake_edge_tts(monkeypatch)
    audio = tts.synthesize_narration(narration)
    profile_path = audio.with_suffix(".voice.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile[0] = "dynamic-v2"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    calls = _fake_edge_tts(monkeypatch, payload=b"new-neural-voice")
    assert tts.synthesize_narration(narration).read_bytes() == b"new-neural-voice"
    assert len(calls) == 1


def test_network_failure_does_not_cache_alternate_voice(tmp_path, monkeypatch):
    narration = _write_narration(tmp_path)
    def fail(*args, **kwargs):
        raise ConnectionError("offline")
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=fail))
    with pytest.raises(RuntimeError, match="在线语音"):
        tts.synthesize_narration(narration)
    assert not narration.with_name("narration.mp3").exists()


def test_windows_system_proxy_is_passed_explicitly(tmp_path, monkeypatch):
    monkeypatch.delenv("BASKETBALL_TTS_PROXY", raising=False)
    monkeypatch.setattr(tts, "getproxies", lambda: {"https": "http://127.0.0.1:7888"})
    calls = _fake_edge_tts(monkeypatch)
    tts.synthesize_narration(_write_narration(tmp_path))
    assert calls[0]["proxy"] == "http://127.0.0.1:7888"
    assert calls[0]["connect_timeout"] == 8
    monkeypatch.setenv("BASKETBALL_TTS_PROXY", "direct")
    assert tts._speech_proxy() is None
    monkeypatch.setenv("BASKETBALL_TTS_PROXY", "127.0.0.1:9999")
    assert tts._speech_proxy() == "http://127.0.0.1:9999"


def test_transient_network_error_retries_without_caching_partial_audio(tmp_path, monkeypatch):
    attempts = []
    class Voice:
        def __init__(self, *args, **kwargs):
            attempts.append(args)
        async def stream(self):
            if len(attempts) == 1:
                yield {"type": "audio", "data": b"partial"}
                raise ConnectionError("transient")
            yield {"type": "audio", "data": b"complete"}
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Voice))
    monkeypatch.setattr(tts, "_RETRY_DELAY", 0)
    audio = tts.synthesize_narration(_write_narration(tmp_path))
    assert audio.read_bytes() == b"complete"
    assert len(attempts) == 2


def test_stalled_synthesis_times_out_without_writing_cache(tmp_path, monkeypatch):
    import asyncio
    class Voice:
        def __init__(self, *args, **kwargs): pass
        async def stream(self):
            await asyncio.sleep(10)
            yield {"type": "audio", "data": b"late"}
    monkeypatch.setitem(sys.modules, "edge_tts", SimpleNamespace(Communicate=Voice))
    monkeypatch.setattr(tts, "_REQUEST_TIMEOUT", .01)
    monkeypatch.setattr(tts, "_RETRY_DELAY", 0)
    narration = _write_narration(tmp_path)
    with pytest.raises(RuntimeError, match="在线语音"):
        tts.synthesize_narration(narration)
    assert not narration.with_name("narration.mp3").exists()
