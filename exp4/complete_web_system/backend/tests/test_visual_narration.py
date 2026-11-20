import json
import re
from types import SimpleNamespace

import pytest

from worker import visual_narration as visual


def test_visual_commentary_uses_actual_frames_at_each_cue(monkeypatch, tmp_path):
    class Capture:
        def get(self, key):
            return 25 if key == visual.cv2.CAP_PROP_FPS else 326

        def release(self):
            pass

    captured = []

    class Grabber:
        def __init__(self, _):
            pass

        def jpeg_b64(self, timestamp):
            captured.append(timestamp)
            return f"frame-at-{timestamp}"

        def close(self):
            pass

    calls = []

    class Model:
        def invoke(self, messages):
            content = messages[0][1]
            starts = [int(re.search(r"start_ms=(\d+)", item["text"]).group(1))
                      for item in content if item["type"] == "text" and "指定时段start_ms=" in item["text"]]
            calls.append(content)
            return SimpleNamespace(content=json.dumps({"sections": [
                {"start_ms": start, "text": "绿衣持球推进，白衣紧跟防守。"} for start in starts
            ]}, ensure_ascii=False))

    monkeypatch.setattr(visual.cv2, "VideoCapture", lambda _: Capture())
    monkeypatch.setattr(visual, "FrameGrabber", Grabber)
    result = visual.generate_visual_narration("task", tmp_path / "source.mp4",
        [{"t_ms": 8000}, {"t_ms": 9500}], model_factory=Model)
    assert result["source"] == "vision"
    assert [s["start_ms"] for s in result["sections"]] == [0, 3000, 6000, 9000, 12000]
    assert result["sections"][-1]["end_ms"] == 13040
    assert [s["event_count"] for s in result["sections"]] == [0, 0, 1, 1, 0]
    assert captured == [0, 500, 3000, 3500, 6000, 6500, 9000, 9500, 12000, 12500]
    assert len(calls) == 3
    assert all(sum(item["type"] == "image_url" for item in call) <= 4 for call in calls)


@pytest.mark.parametrize("rows", [
    [{"start_ms": 0, "text": "持球推进。"}],
    [{"start_ms": 0, "text": "持球推进。"}, {"start_ms": 3000, "text": "三分命中！"}],
    [{"start_ms": 0, "text": "持球推进。"}, {"start_ms": 6000, "text": "白衣跟防。"}],
])
def test_visual_commentary_rejects_missing_or_retimed_cues_and_unsupported_scores(rows):
    with pytest.raises(ValueError):
        visual.parse_sections(json.dumps({"sections": rows}), [0, 3000])


def test_retry_existing_task_regenerates_from_source_video(monkeypatch, tmp_path):
    from worker import narration_service

    (tmp_path / "source.mp4").write_bytes(b"video")
    events = tmp_path / "events.jsonl"
    events.write_text('{"t_ms":9000,"type":"action","action":"pass"}\n', encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings", SimpleNamespace(vision_caption_enabled=True))
    monkeypatch.setattr("app.db.task_repo.get_task", lambda _: {"metadata": {}})
    expected = {"status": "ready", "source": "vision", "sections": [], "text": "当前画面"}
    monkeypatch.setattr(visual, "generate_visual_narration", lambda *args: expected)
    monkeypatch.setattr(narration_service, "generate_narration", lambda *args, **kwargs: pytest.fail("must use pictures"))
    assert narration_service.run_task_narration("task", events) == expected
    assert json.loads((tmp_path / "narration.json").read_text(encoding="utf-8")) == expected


def test_visual_cues_prepare_audio_before_becoming_ready(monkeypatch, tmp_path):
    from worker import narration_service

    (tmp_path / "source.mp4").write_bytes(b"video")
    events = tmp_path / "events.jsonl"
    events.write_text('{"t_ms":0,"type":"action"}\n', encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings", SimpleNamespace(vision_caption_enabled=True))
    monkeypatch.setattr("app.db.task_repo.get_task", lambda _: {"metadata": {}})
    expected = {"status": "ready", "source": "vision", "sections": [{"start_ms": 0, "text": "持球推进。"}], "text": "持球推进。"}
    monkeypatch.setattr(visual, "generate_visual_narration", lambda *args: expected)
    seen = []

    def synthesize(path, section):
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "running"
        audio = path.with_name(f"narration-section-{section}.mp3")
        audio.write_bytes(b"audio")
        seen.append(audio)
        return audio

    monkeypatch.setattr("app.tts.synthesize_narration", synthesize)
    narration_service.run_task_narration("task", events)
    assert len(seen) == 1
    assert seen[0].stat().st_mtime_ns >= (tmp_path / "narration.json").stat().st_mtime_ns
    assert json.loads((tmp_path / "narration.json").read_text(encoding="utf-8"))["status"] == "ready"
