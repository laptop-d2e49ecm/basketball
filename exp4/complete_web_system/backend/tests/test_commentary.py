# -*- coding: utf-8 -*-
"""视频解说的最小单元测试：默认 stub、异常回退、去重与上限。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from worker.commentary import llm as llm_mod
from worker.commentary.llm import LLMCommentaryService
from worker.commentary.stub import StubCommentaryService
from worker import video_service


def test_build_commentary_service_defaults_to_stub(monkeypatch):
    """未配置 BASKETBALL_COMMENTARY 时必须走模板句（无 key 的机器也能跑）。"""
    monkeypatch.setattr(video_service, "settings", SimpleNamespace(commentary_backend="stub"))
    assert isinstance(video_service.build_commentary_service(), StubCommentaryService)


def test_build_commentary_service_selects_llm(monkeypatch):
    monkeypatch.setattr(video_service, "settings", SimpleNamespace(commentary_backend="llm"))
    assert isinstance(video_service.build_commentary_service(), LLMCommentaryService)


def test_llm_falls_back_when_invoke_raises(monkeypatch):
    """LLM 异常时必须回退模板句，且计入 fallbacks。"""
    event = {"t_ms": 5000, "type": "group_direction_change", "player_count": 5}

    monkeypatch.setattr(
        LLMCommentaryService,
        "_invoke",
        lambda self, prompt: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    svc = LLMCommentaryService()
    text = svc.generate(event)
    assert text == StubCommentaryService().generate(event)
    assert svc.stats["fallbacks"] == 1
    assert svc.stats["llm_calls"] == 0
    svc.close()


def test_llm_dedupes_same_key_within_gap(monkeypatch):
    """同类型同人数 5 秒内只调用一次，第二次复用上一条文案。"""
    calls = {"n": 0}

    def fake_invoke(self, prompt):
        calls["n"] += 1
        return f"第 {calls['n']} 次调用"

    monkeypatch.setattr(LLMCommentaryService, "_invoke", fake_invoke)
    svc = LLMCommentaryService(min_gap_ms=5000)
    a = svc.generate({"t_ms": 1000, "type": "player_count", "player_count": 6})
    b = svc.generate({"t_ms": 3000, "type": "player_count", "player_count": 6})
    assert a == b == "第 1 次调用"
    assert calls["n"] == 1
    assert svc.stats["deduped"] == 1
    svc.close()


def test_llm_respects_max_calls(monkeypatch):
    """超过单任务上限后直接回退模板句，不再调用模型。"""
    calls = {"n": 0}

    def fake_invoke(self, prompt):
        calls["n"] += 1
        return "ok"

    monkeypatch.setattr(LLMCommentaryService, "_invoke", fake_invoke)
    svc = LLMCommentaryService(max_calls=1, min_gap_ms=0)
    svc.generate({"t_ms": 1000, "type": "player_count", "player_count": 6})
    text = svc.generate({"t_ms": 9000, "type": "player_cluster", "player_count": 3})
    assert calls["n"] == 1
    assert text == StubCommentaryService().generate({"type": "player_cluster", "player_count": 3})
    assert svc.stats["fallbacks"] == 1
    svc.close()


def test_facts_do_not_leak_unknown_fields():
    """提示词事实只包含事件里给出的信息。"""
    facts = llm_mod._facts({"t_ms": 12400, "type": "player_count", "player_count": 6})
    assert "12.4" in facts and "6" in facts
    assert "比分" not in facts and "投篮" not in facts


def test_prompt_injects_scene_and_style(monkeypatch):
    """画面观察（视觉描述）与真人语气参考都必须进入提示词。"""
    monkeypatch.setattr(llm_mod, "_style_lines", lambda q: ["好球！这波推进打得太快了！", "外线果断出手！"])
    svc = LLMCommentaryService()
    event = {"t_ms": 3000, "type": "player_cluster", "player_count": 4, "scene": "右侧三名球员围抢，球在人堆里"}
    prompt = svc._prompt(event)
    assert "画面观察" in prompt and "右侧三名球员" in prompt
    assert "真人解说语气参考" in prompt and "这波推进" in prompt
    assert svc.stats["style_used"] == 1
    svc.close()


def test_batch_prompt_styles_match_each_action(monkeypatch):
    """批量模式：批内多种事件（动作优先）各自匹配语气参考，不再只看第一条事件。"""
    styles = {
        "篮球 三分出手": ["三分线外果断拔起！"],
        "篮球 传球": ["球转移得干脆利落！"],
        "篮球 运球": ["节奏压得稳稳的。"],
        "篮球 抢断": ["断得干净！"],
        "球员上场站位": ["双方摆开了阵型。"],
    }

    monkeypatch.setattr(llm_mod, "_style_lines", lambda q: styles.get(q, []))
    svc = LLMCommentaryService()
    events = [
        {"t_ms": 1000, "type": "player_count", "player_count": 10},
        {"t_ms": 3000, "type": "action", "action": "shot_3p", "action_zh": "三分出手", "conf": 0.8},
        {"t_ms": 6000, "type": "action", "action": "pass", "action_zh": "传球", "conf": 0.8},
    ]
    prompt = svc._batch_prompt(events)
    assert "果断拔起" in prompt and "干脆利落" in prompt  # 两种动作各自有参考
    assert "双方摆开了阵型" in prompt  # 第三种查询（人数事件）也在上限内
    assert svc.stats["style_used"] == 1

    capped = svc._batch_prompt([
        {"t_ms": i, "type": "action", "action": f"a{i}", "action_zh": zh, "conf": 0.8}
        for i, zh in enumerate(["三分出手", "传球", "运球", "抢断"], 1)
    ])
    assert "断得干净" not in capped  # 查询种数封顶 3：第 4 种动作不取参考
    assert "运球" in capped and capped.count("参考") == 1
    svc.close()


def test_vision_disabled_without_video_path():
    """未传 video_path（如聊天回放、单测）时不抓帧、不调视觉。"""
    svc = LLMCommentaryService()
    assert svc._grabber is None
    assert svc._scene_for({"t_ms": 1000, "type": "player_count", "player_count": 5}) is None
    assert svc.stats["vision_calls"] == 0
    svc.close()


def test_batch_generates_one_call_for_whole_batch(monkeypatch):
    """批量模式：整批一次调用，行号解析后逐条落位。"""
    monkeypatch.setattr(llm_mod, "_MODEL_COOLDOWN_UNTIL", 0.0)
    calls = {"n": 0}

    def fake_invoke_batch(self, prompt, n):
        calls["n"] += 1
        return ["第一条", "第二条", "第三条"][:n]

    monkeypatch.setattr(LLMCommentaryService, "_invoke_batch", fake_invoke_batch)
    svc = LLMCommentaryService(min_gap_ms=0)
    events = [
        {"t_ms": 1000, "type": "player_count", "player_count": 6},
        {"t_ms": 9000, "type": "player_cluster", "player_count": 4},
        {"t_ms": 17000, "type": "player_count_change", "player_count": 8},
    ]
    texts = svc.generate_batch(events)
    assert texts == ["第一条", "第二条", "第三条"]
    assert calls["n"] == 1
    assert svc.stats["llm_calls"] == 1
    svc.close()


def test_batch_fills_missing_lines_with_fallback(monkeypatch):
    """模型少给行时，缺的行用模板句补齐，已有行保留。"""
    monkeypatch.setattr(llm_mod, "_MODEL_COOLDOWN_UNTIL", 0.0)

    def fake_invoke_batch(self, prompt, n):
        return ["只有第一条"]  # 少给了

    monkeypatch.setattr(LLMCommentaryService, "_invoke_batch", fake_invoke_batch)
    svc = LLMCommentaryService(min_gap_ms=0)
    events = [
        {"t_ms": 1000, "type": "player_count", "player_count": 6},
        {"t_ms": 9000, "type": "player_cluster", "player_count": 4},
    ]
    texts = svc.generate_batch(events)
    assert texts[0] == "只有第一条"
    assert "聚到了一块" in texts[1]  # 模板句补齐
    svc.close()


def test_quota_error_triggers_cooldown(monkeypatch):
    """403/额度错误后进入冷却：后续事件不再尝试调用，直接模板句。"""
    monkeypatch.setattr(llm_mod, "_MODEL_COOLDOWN_UNTIL", 0.0)
    attempts = {"n": 0}

    def fake_invoke(self, prompt):
        attempts["n"] += 1
        raise RuntimeError("Error code: 403 - 免费请求额度已用完")

    monkeypatch.setattr(LLMCommentaryService, "_invoke", fake_invoke)
    svc = LLMCommentaryService(min_gap_ms=0)
    a = svc.generate({"t_ms": 1000, "type": "player_count", "player_count": 6})
    assert attempts["n"] == 1 and a == StubCommentaryService().generate({"type": "player_count", "player_count": 6})
    b = svc.generate({"t_ms": 9000, "type": "player_cluster", "player_count": 4})
    assert attempts["n"] == 1 and b == StubCommentaryService().generate({"type": "player_cluster", "player_count": 4})  # 冷却期内零尝试
    assert llm_mod._MODEL_COOLDOWN_UNTIL > 0
    monkeypatch.setattr(llm_mod, "_MODEL_COOLDOWN_UNTIL", 0.0)  # 还原，避免影响其他测试
    svc.close()
