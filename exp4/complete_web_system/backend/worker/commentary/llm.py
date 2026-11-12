# -*- coding: utf-8 -*-
"""LLM 解说实现：把视频事件交给大模型，写成一句直播解说。

设计要点（对应任务书“视频解说 LLM 化”）：
1. 客户端进程内复用（模块级缓存），不按事件新建；
2. 单次调用硬超时 10 秒（线程池兜底，避免客户端自身超时不生效）；
3. 任何异常 / 超时 / 未配置 key，都静默回退到 StubCommentaryService，绝不让 Worker 崩；
4. 两条护栏：同类型事件 5 秒内只调一次（复用上一条文案）、单任务最多 8 次 LLM 调用；
5. 只允许使用事件里的事实，提示词明确禁止编造投篮、比分、球员姓名等。
"""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from worker.commentary.base import CommentaryService
from worker.commentary.stub import StubCommentaryService

logger = logging.getLogger("basketball-worker.commentary")

SYSTEM_PROMPT = (
    "你是篮球比赛的现场解说员，说话简短、口语化、有现场感。"
    "你只能依据本条事件给出的事实说话，绝对不许出现事实里没有的信息："
    "不许说比分、投篮命中、罚球、球员姓名、球队名、战术名，也不许说"
    "'时间走完''比赛结束''暂停''犯规'这类事件里没有的情节，"
    "也不许说'最后''终场''压哨''节末'这类赛况判断。"
    "不要复述其他时间点的事件，只解说本条。"
    "说法要有变化：不要每条都用'人数变成X'，可以换'场上现在…''这边…''一下…'等不同说法。"
    "输出只要一句解说词（不超过 30 字），不要引号、不要解释、不要分点。"
)

_TYPE_TEXT = {
    "player_count": "画面球员人数",
    "player_count_change": "画面球员人数发生变化",
    "player_count_snapshot": "画面球员人数",
    "player_cluster": "画面局部球员聚集",
    "group_direction_change": "球员整体移动方向发生反转",
}

_MODEL = None
_MODEL_FAILED = False


def _get_model() -> Any | None:
    """进程内复用的模型客户端；初始化失败只记一次日志。"""
    global _MODEL, _MODEL_FAILED
    if _MODEL is not None:
        return _MODEL
    if _MODEL_FAILED:
        return None
    try:
        from app.agent.providers import make_chat_model

        _MODEL = make_chat_model()
        logger.info("commentary LLM 客户端已初始化（进程内复用）")
        return _MODEL
    except Exception as exc:  # noqa: BLE001 - 配置缺失不影响主流程
        _MODEL_FAILED = True
        logger.warning("commentary LLM 初始化失败，将回退模板句：%s", exc)
        return None


def _fmt_sec(t_ms: Any) -> str:
    try:
        seconds = float(t_ms) / 1000.0
    except (TypeError, ValueError):
        return "开场"
    return "开场" if seconds < 1 else f"{seconds:.1f}"


def _facts(event: dict[str, Any], prev: dict[str, Any] | None = None) -> str:
    kind = str(event.get("type", ""))
    count = event.get("player_count")
    desc = _TYPE_TEXT.get(kind, kind or "画面事件")
    sec = _fmt_sec(event.get("t_ms"))
    prev_count = (prev or {}).get("player_count")
    lead = f"第 {sec} 秒" if sec != "开场" else "开场时"
    if count is None:
        return f"{lead}，{desc}。"
    if kind == "player_cluster":
        return f"{lead}，画面局部有 {count} 名球员聚在一起。"
    if kind == "player_count_change" and prev_count is not None and prev_count != count:
        return f"{lead}，画面球员人数由 {prev_count} 人变为 {count} 人。"
    return f"{lead}，场上共 {count} 名球员。"


def _clean(text: Any) -> str:
    s = str(text or "").strip()
    s = re.sub(r"^[“”\"'「」\s]+|[“”\"'「」\s]+$", "", s)
    s = s.replace("\n", " ").strip()
    s = re.sub(r"^(解说[:：]?\s*)", "", s)
    return s[:60]


class LLMCommentaryService(CommentaryService):
    """大模型解说；失败一律回退模板句。"""

    def __init__(
        self,
        timeout_s: float = 10.0,
        min_gap_ms: int = 5000,
        max_calls: int = 12,  # 可被 BASKETBALL_COMMENTARY_MAX_CALLS 覆盖
        fallback: CommentaryService | None = None,
    ) -> None:
        self._fallback = fallback or StubCommentaryService()
        self._timeout_s = timeout_s
        self._min_gap_ms = min_gap_ms
        try:
            max_calls = int(os.getenv("BASKETBALL_COMMENTARY_MAX_CALLS", str(max_calls)))
        except ValueError:
            pass
        self._max_calls = max_calls
        self._calls = 0
        self._fallbacks = 0
        self._deduped = 0
        self._last: dict[tuple[str, Any], tuple[int, str]] = {}
        self._last_sec = 0.0
        self._prev: dict[str, Any] | None = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="commentary")

    # ---- 统计（任务结束时打一行日志，报告里可用）----
    @property
    def stats(self) -> dict[str, int]:
        return {
            "llm_calls": self._calls,
            "fallbacks": self._fallbacks,
            "deduped": self._deduped,
        }

    def _prompt(self, event: dict[str, Any]) -> str:
        facts = _facts(event, self._prev)
        return facts + "\n只解说这一条，不超过 30 字。"

    def _invoke(self, prompt: str) -> str:
        model = _get_model()
        if model is None:
            raise RuntimeError("模型客户端不可用")
        msg = model.invoke([("system", SYSTEM_PROMPT), ("user", prompt)])
        return _clean(getattr(msg, "content", msg))

    def generate(self, event: dict[str, Any]) -> str:
        kind = str(event.get("type", ""))
        count = event.get("player_count")
        sec = event.get("t_ms") or 0
        key = (kind, count if kind in {"player_cluster", "player_count", "player_count_snapshot", "player_count_change"} else None)

        # 护栏 1：同类型事件冷却期内复用上一条文案
        last = self._last.get(key)
        try:
            age_ms = float(sec) - float(last[0]) if last else 1e18
        except (TypeError, ValueError):
            age_ms = 1e18
        if last and age_ms < self._min_gap_ms:
            self._deduped += 1
            self._prev = event
            return last[1]

        # 护栏 2：单任务调用上限
        if self._calls >= self._max_calls:
            self._fallbacks += 1
            self._prev = event
            return self._fallback.generate(event)

        started = time.perf_counter()
        try:
            future = self._executor.submit(self._invoke, self._prompt(event))
            text = future.result(timeout=self._timeout_s)
            if not text:
                raise RuntimeError("空输出")
            self._calls += 1
            self._last[key] = (int(float(sec)), text)
            self._last_sec = time.perf_counter() - started
            logger.info(
                "commentary LLM ok type=%s %.2fs -> %s", kind, self._last_sec, text[:30]
            )
            self._prev = event
            return text
        except FutureTimeout:
            self._fallbacks += 1
            logger.warning("commentary LLM 超时（>%.0fs），回退模板句 type=%s", self._timeout_s, kind)
        except Exception as exc:  # noqa: BLE001 - 任何失败都要保住任务
            self._fallbacks += 1
            logger.warning("commentary LLM 失败，回退模板句 type=%s err=%s", kind, exc)
        self._prev = event
        return self._fallback.generate(event)

    def close(self) -> None:
        self._executor.shutdown(wait=False)
