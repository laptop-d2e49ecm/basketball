import json
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import narration_timeline as timeline


def _tone(path: Path, seconds: float, frequency: int):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        samples = [round(9000 * math.sin(i * 2 * math.pi * frequency / 24000)) for i in range(round(seconds * 24000))]
        audio.writeframes(struct.pack("<" + "h" * len(samples), *samples))


def test_timeline_preserves_pitch_and_timestamps_without_changing_source_voice(tmp_path, monkeypatch):
    import imageio_ffmpeg

    parts = [tmp_path / "first.wav", tmp_path / "second.wav"]
    _tone(parts[0], 3, 440)
    _tone(parts[1], 2, 660)
    source_bytes = [path.read_bytes() for path in parts]
    path = tmp_path / "narration.json"
    path.write_text(json.dumps({"sections": [
        {"start_ms": 500, "end_ms": 1500, "text": "第一段"},
        {"start_ms": 1500, "end_ms": 3500, "text": "第二段"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(timeline, "synthesize_narration", lambda _, section: parts[section])
    track = timeline.synthesize_timeline(path)
    exe = imageio_ffmpeg.get_ffmpeg_exe()

    def samples():
        raw = timeline._run([exe, "-v", "error", "-i", str(track), "-ac", "1", "-ar", "24000", "-f", "s16le", "pipe:1"])
        return struct.unpack("<" + "h" * (len(raw) // 2), raw)

    values = samples()
    assert abs(len(values) / 24000 - 3.5) < .05
    assert max(abs(value) for value in values[:int(.4 * 24000)]) < 100

    def frequency(start, end):
        window = values[round(start * 24000):round(end * 24000)]
        crossings = sum(a <= 0 < b for a, b in zip(window, window[1:]))
        return crossings / (end - start)

    assert 420 < frequency(.7, 1.3) < 460  # Tempo changes must preserve pitch.
    assert 640 < frequency(1.8, 3.1) < 680
    boundary = values[round(1.46 * 24000):round(1.54 * 24000)]
    assert (sum(value * value for value in boundary) / len(boundary)) ** .5 > 3000
    assert [file.read_bytes() for file in parts] == source_bytes
    first_mtime = track.stat().st_mtime_ns
    assert timeline.synthesize_timeline(path).stat().st_mtime_ns == first_mtime
    _tone(parts[1], 2, 880)
    timeline.synthesize_timeline(path)
    values = samples()
    assert 860 < frequency(1.8, 3.1) < 900


def test_timeline_endpoint_serves_aligned_track(tmp_path, monkeypatch):
    from app.api import tasks

    folder = tmp_path / "task"
    folder.mkdir()
    (folder / "narration.json").write_text('{"status":"ready"}', encoding="utf-8")
    target = folder / "narration-timeline.mp3"
    target.write_bytes(b"track")
    monkeypatch.setattr(tasks, "settings", SimpleNamespace(runs_dir=tmp_path))
    monkeypatch.setattr(tasks.task_repo, "get_task", lambda _: {"status": "ready"})
    monkeypatch.setattr(timeline, "synthesize_timeline", lambda _: target)
    assert tasks.get_narration_audio("task", timeline=True).path == target
    with pytest.raises(Exception, match="503"):
        tasks.get_narration_audio("task", section=0, timeline=True)


def test_timeline_rejects_missing_time_ranges(tmp_path):
    path = tmp_path / "narration.json"
    path.write_text('{"sections":[{"start_ms":0}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="时间范围"):
        timeline.synthesize_timeline(path)
