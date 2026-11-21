import json
import re
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from worker import visual_narration as visual


@pytest.mark.parametrize("failed", [False, True])
def test_parallel_narration_reuses_result_and_falls_back_without_repeating_vision(monkeypatch, tmp_path, failed):
    from worker import narration_service

    events = tmp_path / "events.jsonl"
    events.write_text('{"t_ms":0}\n{"t_ms":3000}\n', encoding="utf-8")
    monkeypatch.setattr("app.db.task_repo.get_task", lambda _: {"metadata": {}})
    monkeypatch.setattr(visual, "generate_visual_narration", lambda *args: pytest.fail("must not repeat vision"))
    fallback = {"status": "ready", "source": "agent", "sections": [], "text": "事件解说"}
    monkeypatch.setattr(narration_service, "generate_narration", lambda *args, **kwargs: fallback)
    monkeypatch.setattr("app.tts.synthesize_narration", lambda *args: None)
    future = Future()
    if failed:
        future.set_exception(RuntimeError("vision unavailable"))
    else:
        future.set_result({"status": "ready", "source": "vision", "text": "画面解说", "sections": [
            {"start_ms": 0, "end_ms": 3000, "event_count": 0, "text": "持球推进。"},
            {"start_ms": 3000, "end_ms": 6000, "event_count": 0, "text": "紧跟防守。"},
        ]})
    result = narration_service.run_task_narration("task", events, visual_future=future)
    if failed:
        assert result == fallback
    else:
        assert result["event_count"] == 2
        assert [row["event_count"] for row in result["sections"]] == [1, 1]
    assert json.loads((tmp_path / "narration.json").read_text(encoding="utf-8"))["status"] == "ready"


@pytest.mark.parametrize("repair", [False, True])
def test_visual_commentary_uses_actual_frames_at_each_cue(monkeypatch, tmp_path, repair):
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
            if repair and len(calls) == 1:
                return SimpleNamespace(content=json.dumps({"sections": [{"start_ms": starts[0], "text": "三分命中！"}]}))
            return SimpleNamespace(content=json.dumps({"sections": [
                {"start_ms": start, "text": "绿衣持球推进，白衣紧跟防守。"} for start in starts
            ]}, ensure_ascii=False))

    monkeypatch.setattr(visual.cv2, "VideoCapture", lambda _: Capture())
    monkeypatch.setattr(visual, "FrameGrabber", Grabber)
    result = visual.generate_visual_narration("task", tmp_path / "source.mp4",
        [{"t_ms": 8000}, {"t_ms": 9500}], model_factory=Model)
    assert result["source"] == "vision"
    assert [s["start_ms"] for s in result["sections"]] == [0, 6000, 12000]
    assert result["sections"][-1]["end_ms"] == 13040
    assert [s["event_count"] for s in result["sections"]] == [0, 2, 0]
    assert captured == [2000, 2500, 4000, 4500, 8000, 8500, 10000, 10500, 12346, 12519, 12693, 12866]
    assert len(calls) == 4 + int(repair)
    assert all(sum(item["type"] == "image_url" for item in call) <= 4 for call in calls)


def test_spoken_rewrite_keeps_time_and_rejects_new_actions():
    facts = [
        {"start_ms": 0, "text": "绿衣持球推进，白衣紧跟防守。"},
        {"start_ms": 3000, "text": "绿衣右侧突破，白衣紧跟防守。"},
        {"start_ms": 6000, "text": "白衣33号弧顶护球。"},
    ]

    class Model:
        def invoke(self, _):
            return SimpleNamespace(content=json.dumps({"sections": [
                {"start_ms": 0, "text": "绿衣推反击！白衣回追。"},
                {"start_ms": 3000, "text": "往里这一步！白衣跟得很紧。"},
                {"start_ms": 6000, "text": "白衣26号起手投篮！"},
            ]}))

    result = visual.polish_sections(Model(), facts)
    assert [row["start_ms"] for row in result] == [0, 3000, 6000]
    assert result[0]["text"] == facts[0]["text"]  # 推进 cannot become 反击.
    assert result[1]["text"] == "往里这一步！白衣跟得很紧。"
    assert result[2]["text"] == facts[2]["text"]  # No new jersey number or shot.


def test_rewrite_preserves_observed_shot_but_does_not_invent_one():
    assert visual._faithful_rewrite("白衣投篮出手，绿衣跟防。", "白衣投篮，绿衣跟防。")
    assert not visual._faithful_rewrite("白衣起跳，绿衣跟防。", "白衣投篮出手，绿衣跟防。")
    assert not visual._faithful_rewrite("白衣投篮出手。", "白衣举手。")
    assert not visual._faithful_rewrite("白衣投篮命中！", "白衣投篮出手。")
    with pytest.raises(ValueError):
        visual.parse_sections('{"sections":[{"start_ms":0,"text":"把球送进篮筐。"}]}', [0])


@pytest.mark.parametrize("start,end", [(0, 6000), (12000, 13040), (0, 200)])
def test_motion_pairs_stay_inside_cue_with_four_image_budget(start, end):
    times = visual.cue_frame_times(start, end)
    assert len(times) == 4
    assert all(start <= t < end for t in times)
    assert times[1] - times[0] <= 500
    assert times[3] - times[2] <= 500


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


@pytest.mark.parametrize("source", ["vision", "agent"])
def test_visual_cues_prepare_audio_before_becoming_ready(monkeypatch, tmp_path, source):
    from worker import narration_service

    (tmp_path / "source.mp4").write_bytes(b"video")
    events = tmp_path / "events.jsonl"
    events.write_text('{"t_ms":0,"type":"action"}\n', encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings", SimpleNamespace(vision_caption_enabled=True))
    monkeypatch.setattr("app.db.task_repo.get_task", lambda _: {"metadata": {}})
    expected = {"status": "ready", "source": source, "sections": [{"start_ms": 0, "text": "持球推进。"}], "text": "持球推进。"}
    def visual_result(*args):
        if source == "agent":
            raise RuntimeError("vision unavailable")
        return expected

    monkeypatch.setattr(visual, "generate_visual_narration", visual_result)
    monkeypatch.setattr(narration_service, "generate_narration", lambda *args, **kwargs: expected)
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
