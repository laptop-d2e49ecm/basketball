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
    assert text.startswith("画面局部出现")
    assert svc.stats["fallbacks"] == 1
    svc.close()


def test_facts_do_not_leak_unknown_fields():
    """提示词事实只包含事件里给出的信息。"""
    facts = llm_mod._facts({"t_ms": 12400, "type": "player_count", "player_count": 6})
    assert "12.4" in facts and "6" in facts
    assert "比分" not in facts and "投篮" not in facts
