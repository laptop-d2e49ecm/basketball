# -*- coding: utf-8 -*-
"""LLM 解说实现：把视频事件交给大模型，写成一句直播解说。

设计要点（对应任务书“视频解说 LLM 化”）：
1. 客户端进程内复用（模块级缓存），不按事件新建；
2. 单次调用硬超时（线程池兜底，避免客户端自身超时不生效）；
3. 任何异常 / 超时 / 未配置 key，都静默回退到 StubCommentaryService，绝不让 Worker 崩；
4. 护栏：同类型事件冷却期内复用上一条文案、单任务调用上限、批量生成（默认 5 条/次，配额消耗降为 1/N）；
5. 事实两层：结构化事件事实 + 视觉模型对事件时刻关键帧的客观描述（可选，BASKETBALL_VISION_CAPTIONS；
   同一 5 秒时间桶内的事件共用一次画面观察，进一步省配额）；
6. 风格一层：从 3 万条真人解说语料检索原句做语气参考（只学语气不抄事实）；
   单条按本条事件检索，批量按批内多种事件（动作优先）各取参考，不只看第一条；
7. 配额熔断：403/429/额度类错误后进程内冷却 10 分钟，期间直接走模板句，不再逐条硬撞。
"""
from __future__ import annotations

import logging
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
    "你只能依据本条事件给出的事实说话（包括'画面观察'对截图的客观描述）。"
    "动作识别事件给出的动作（如三分出手、运球、传球、抢断）属于事实，可以解说，"
    "但只许用事实里给出的那一个动作，不许引申出别的动作或结果；"
    "除此之外，绝对不许出现事实里没有的信息："
    "不许说比分、投篮命中与否、球员姓名、球队名"
    "（若事实里给出'用户提供的对阵与比分'，其中给出的队名和比分可以直接使用），也不许说"
    "'时间走完''比赛结束''暂停''犯规'这类事实里没有的情节，"
    "也不许说'最后''终场''压哨''节末'这类赛况判断，"
    "更不许推测接下来会发生什么（例如'马上要发球''要进攻了''准备投篮'）。"
    "若给出真人解说语气参考：只学它的语气、节奏和用词习惯，"
    "参考句里的比分、人名、球队和情节一律不许搬用。"
    "不要复述其他时间点的事件，只解说本条；"
    "若给出'上文解说'，只用于自然衔接和避免重复，不要复述其内容。"
    "说法要有变化：不要每条都用'人数变成X'，可以换'场上现在…''这边…''一下…'等不同说法。"
    "解说词必须是完整的一句话：不许只写动作名或'动作名+感叹号'（如'传球！'），"
    "要带上位置、人数或节奏等本条事实里的细节；同类动作再次出现时必须换一种说法。"
    "输出只要一句解说词（不超过 30 字），不要引号、不要解释、不要分点。"
)

BATCH_SYSTEM_PROMPT = SYSTEM_PROMPT + (
    "\n现在是批量模式：输入共 N 条事件，你输出 N 行，第 k 行对应第 k 条事件，"
    "每行以行号数字开头（如'1. ''2. '），行内只要该条的解说词本身。"
)

_TYPE_TEXT = {
    "player_count": "画面球员人数",
    "player_count_change": "画面球员人数发生变化",
    "player_count_snapshot": "画面球员人数",
    "player_cluster": "画面局部球员聚集",
    "group_direction_change": "球员整体移动方向发生反转",
}

# 无画面观察时的风格检索关键词（按事件类型）
_TYPE_QUERY = {
    "player_count": "球员上场站位",
    "player_count_snapshot": "球员站位",
    "player_count_change": "换人 球员上场 回防",
    "player_cluster": "篮下包夹 围抢",
    "group_direction_change": "快攻推进 攻防转换",
}

_STYLE_MAX = 2
_STYLE_QUERIES_MAX = 3  # 批量模式下最多为几种事件各取语气参考
_SCENE_BUCKET_MS = 5000  # 同一 5 秒桶内的事件共用一次画面观察
_QUOTA_COOLDOWN_S = 600.0  # 配额类错误后的进程级冷却
_style_failed = False

_MODEL = None
_MODEL_FAILED = False
_MODEL_COOLDOWN_UNTIL = 0.0  # 配额熔断：到期前不再尝试调用


def _quota_hit(exc: BaseException) -> bool:
    """识别配额/限流类错误（免费中转 24 小时窗口、平台限流等）。"""
    s = str(exc)
    return any(k in s for k in ("403", "429", "额度", "quota", "rate limit", "rate_limit"))


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


def _style_lines(query: str) -> list[str]:
    """从真人解说语料检索 2 条语气参考；语料缺失或检索失败时返回空列表（进程内熔断）。"""
    global _style_failed
    if _style_failed or not query.strip():
        return []
    try:
        from app.agent.tools import _commentary_index

        index = _commentary_index()
        if index is None:
            _style_failed = True
            logger.info("解说语料未配置，本进程关闭风格参考")
            return []
        qv = index["vectorizer"].transform([query.strip()])
        sims = (qv @ index["matrix"].T).toarray().ravel()
        if float(sims.max()) < 0.02:
            return []
        order = sims.argsort()[::-1][:_STYLE_MAX]
        return [index["lines"][int(i)] for i in order if sims[int(i)] > 0]
    except Exception as exc:  # noqa: BLE001 - 风格参考是锦上添花，失败只关掉
        _style_failed = True
        logger.warning("风格检索失败，本进程关闭风格参考：%s", exc)
        return []


def content_text(content: Any) -> str:
    """兼容两种模型返回：content 为纯字符串，或内容块列表（如 reasoning + text 块）。

    部分中转/推理模型（OpenAI 兼容端点）会把最终回答放进 [{'type':'text','text':…}]
    块里，直接 str(content) 会把 reasoning 块的加密内容一起转进去。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _context_line(context: dict[str, Any] | None) -> str:
    """用户上传时填写的对阵与比分 → 注入提示词的事实行。

    空值逐项兜底：队名缺哪边就不写哪边；比分必须两边都有才构成事实；
    全部为空时返回空串，提示词完全不出现这一行。
    """
    if not isinstance(context, dict):
        return ""
    team1 = str(context.get("team1") or "").strip()
    team2 = str(context.get("team2") or "").strip()
    score1 = str(context.get("score1") or "").strip()
    score2 = str(context.get("score2") or "").strip()
    parts: list[str] = []
    if team1:
        parts.append(f"主队{team1}")
    if team2:
        parts.append(f"客队{team2}")
    if score1 and score2:
        parts.append(f"比分 {score1}:{score2}")
    if not parts:
        return ""
    return "用户提供的对阵与比分（视为可信事实，其中给出的队名和比分可以直接使用）：" + "，".join(parts) + "。\n"


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
    if kind == "action":
        zh = str(event.get("action_zh") or event.get("action") or "动作")
        conf = event.get("conf")
        tail = f"，模型置信度 {conf:.0%}" if isinstance(conf, float) else ""
        return f"{lead}，动作识别：有球员{zh}{tail}。"
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


def _event_key(event: dict[str, Any]) -> tuple[str, Any]:
    kind = str(event.get("type", ""))
    count = event.get("player_count")
    if kind == "action":
        detail: Any = event.get("action")
    elif kind in {"player_cluster", "player_count", "player_count_snapshot", "player_count_change"}:
        detail = count
    else:
        detail = None
    return (kind, detail)


class LLMCommentaryService(CommentaryService):
    """大模型解说；失败一律回退模板句。

    video_path 提供时（BASKETBALL_VISION_CAPTIONS=on），每条真正生成解说的事件
    会先抓事件时刻关键帧交视觉模型描述，作为"画面观察"事实注入提示词。
    """

    def __init__(
        self,
        timeout_s: float = 10.0,
        min_gap_ms: int = 5000,
        max_calls: int | None = None,  # 默认取 settings.commentary_max_calls
        fallback: CommentaryService | None = None,
        video_path: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._fallback = fallback or StubCommentaryService()
        self._timeout_s = timeout_s
        self._min_gap_ms = min_gap_ms
        self._vision_timeout_s = 20.0
        vision_enabled = False
        vision_max_calls = 0
        try:
            from app.core.config import settings

            if max_calls is None:
                max_calls = int(settings.commentary_max_calls)
            vision_enabled = bool(getattr(settings, "vision_caption_enabled", False))
            vision_max_calls = int(getattr(settings, "vision_max_calls", 16))
        except Exception:  # noqa: BLE001 - 配置缺失时退回保守值
            if max_calls is None:
                max_calls = 12
        self._max_calls = max(1, int(max_calls))
        self._calls = 0
        self._fallbacks = 0
        self._deduped = 0
        self._vision_calls = 0
        self._style_used = 0
        self._last: dict[tuple[str, Any], tuple[int, str]] = {}
        self._last_sec = 0.0
        self._prev: dict[str, Any] | None = None
        self._scene_cache: dict[int, str] = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="commentary")
        self._context = _context_line(context)
        self._recent: list[str] = []  # 最近已播出的解说（批量间衔接用）
        self._grabber = None
        self._vision_budget = 0
        if video_path and vision_enabled:
            from worker.commentary.vision import FrameGrabber

            self._grabber = FrameGrabber(video_path)
            self._vision_budget = max(0, int(vision_max_calls))

    # ---- 统计（任务结束时打一行日志，报告里可用）----
    @property
    def stats(self) -> dict[str, int]:
        return {
            "llm_calls": self._calls,
            "vision_calls": self._vision_calls,
            "style_used": self._style_used,
            "fallbacks": self._fallbacks,
            "deduped": self._deduped,
        }

    # ---- 画面观察（带 5 秒时间桶缓存）----
    def _scene_for(self, event: dict[str, Any]) -> str | None:
        """取事件时刻的画面描述；同一时间桶只抓一次帧、调一次视觉。失败返回 None。"""
        if self._grabber is None or self._vision_calls >= self._vision_budget:
            return None
        t_ms = float(event.get("t_ms") or 0)
        bucket = int(t_ms // _SCENE_BUCKET_MS)
        cached = self._scene_cache.get(bucket)
        if cached is not None:
            return cached
        try:
            jpeg = self._executor.submit(self._grabber.jpeg_b64, t_ms).result(timeout=5.0)
        except FutureTimeout:
            logger.warning("抓帧超时 t_ms=%s，本条跳过画面观察", t_ms)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("抓帧失败 t_ms=%s err=%s", t_ms, exc)
            return None
        if not jpeg:
            return None
        from worker.commentary.vision import describe_frame

        self._vision_calls += 1
        try:
            scene = self._executor.submit(describe_frame, jpeg).result(timeout=self._vision_timeout_s)
        except FutureTimeout:
            logger.warning("画面描述超时（>%.0fs），本条不注入", self._vision_timeout_s)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("画面描述失败：%s", exc)
            return None
        if scene:
            self._scene_cache[bucket] = scene
            logger.info("vision caption ok t=%sms -> %s", int(t_ms), scene[:36])
        return scene or None

    # ---- 提示词 ----
    def _event_block(self, event: dict[str, Any], index: int) -> str:
        parts = [f"事件 {index}：{_facts(event, self._prev)}"]
        scene = str(event.get("scene") or "").strip()
        if scene:
            parts.append(f"画面观察（视觉模型对本时刻截图的客观描述，视为事实）：{scene}")
        return "\n".join(parts)

    def _render_style(self, lines: list[str]) -> str:
        if not lines:
            return ""
        self._style_used += 1
        refs = "\n".join(f"{i}. {s}" for i, s in enumerate(lines, 1))
        return f"真人解说语气参考（只学语气与句式，其中比分/人名/情节不许用）：\n{refs}\n"

    def _style_block(self, query: str) -> str:
        return self._render_style(_style_lines(query))

    def _style_block_for_batch(self, events: list[dict[str, Any]]) -> str:
        """批内每种事件（动作优先）各检索语气参考并去重合并，避免整批只参考第一条。"""
        queries: list[str] = []
        ordered = sorted(events, key=lambda ev: str(ev.get("type", "")) != "action")
        for ev in ordered:
            query = self._query_for(ev)
            if query and query not in queries:
                queries.append(query)
        lines: list[str] = []
        for query in queries[:_STYLE_QUERIES_MAX]:
            for line in _style_lines(query):
                if line and line not in lines:
                    lines.append(line)
        return self._render_style(lines)

    def _query_for(self, event: dict[str, Any]) -> str:
        kind = str(event.get("type", ""))
        if kind == "action":
            zh = str(event.get("action_zh") or event.get("action") or "")
            return f"篮球 {zh}".strip()
        scene = str(event.get("scene") or "").strip()
        return scene if scene else _TYPE_QUERY.get(kind, "篮球比赛 球员")

    def _prompt(self, event: dict[str, Any]) -> str:
        parts = []
        if self._context:
            parts.append(self._context.rstrip("\n"))
        parts.append(self._event_block(event, 1))
        parts.append(self._style_block(self._query_for(event)))
        parts.append("只解说这一条（事件 1），不超过 30 字。")
        return "\n".join(p for p in parts if p)

    def _batch_prompt(self, events: list[dict[str, Any]], recent: list[str] | None = None) -> str:
        blocks = [self._event_block(ev, i + 1) for i, ev in enumerate(events)]
        parts = []
        if self._context:
            parts.append(self._context.rstrip("\n"))
        parts.append("\n".join(blocks))
        parts.append(self._style_block_for_batch(events))
        if recent:
            shown = "；".join(f"{i}. {text}" for i, text in enumerate(recent, 1))
            parts.append(f"上文已播出的解说（只做衔接与避免重复，不要复述）：{shown}")
        parts.append(f"共 {len(events)} 条事件，逐条输出 {len(events)} 行，第 k 行以'k. '开头（k 为行号数字），只要解说词本身。")
        return "\n".join(p for p in parts if p)

    # ---- 调用 ----
    def _invoke(self, prompt: str) -> str:
        model = _get_model()
        if model is None:
            raise RuntimeError("模型客户端不可用")
        msg = model.invoke([("system", SYSTEM_PROMPT), ("user", prompt)])
        return _clean(content_text(getattr(msg, "content", msg)))

    def _invoke_batch(self, prompt: str, n: int) -> list[str]:
        model = _get_model()
        if model is None:
            raise RuntimeError("模型客户端不可用")
        msg = model.invoke([("system", BATCH_SYSTEM_PROMPT), ("user", prompt)])
        content = content_text(getattr(msg, "content", msg) or "")
        lines: list[str] = []
        for raw in content.splitlines():
            s = _clean(raw)
            s = re.sub(r"^(?:\d{1,3}|[a-zA-Z]{1,3})\s*[\.、．)）]\s*", "", s)
            if s:
                lines.append(s)
        return lines[:n]

    # ---- 单条生成（兼容旧调用；批量为默认路径）----
    def generate(self, event: dict[str, Any]) -> str:
        key = _event_key(event)
        sec = event.get("t_ms") or 0

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

        # 护栏 2：单任务调用上限 / 配额熔断冷却
        if self._calls >= self._max_calls or time.time() < _MODEL_COOLDOWN_UNTIL:
            self._fallbacks += 1
            self._prev = event
            return self._fallback.generate(event)

        scene = self._scene_for(event)
        if scene:
            event["scene"] = scene  # 写回事件，落盘 events.jsonl 供前端/Agent 查看画面依据

        started = time.perf_counter()
        try:
            future = self._executor.submit(self._invoke, self._prompt(event))
            text = future.result(timeout=self._timeout_s)
            if not text:
                raise RuntimeError("空输出")
            self._calls += 1
            self._last[key] = (int(float(sec)), text)
            self._recent = [*self._recent, text][-2:]
            self._last_sec = time.perf_counter() - started
            logger.info("commentary LLM ok type=%s %.2fs -> %s", event.get("type"), self._last_sec, text[:30])
            self._prev = event
            return text
        except FutureTimeout:
            self._fallbacks += 1
            logger.warning("commentary LLM 超时（>%.0fs），回退模板句 type=%s", self._timeout_s, event.get("type"))
        except Exception as exc:  # noqa: BLE001 - 任何失败都要保住任务
            self._fallbacks += 1
            if _quota_hit(exc):
                _set_model_cooldown()
            logger.warning("commentary LLM 失败，回退模板句 type=%s err=%s", event.get("type"), exc)
        self._prev = event
        return self._fallback.generate(event)

    # ---- 批量生成（默认路径：一次调用出整批解说，配额消耗 1/N）----
    def generate_batch(self, events: list[dict[str, Any]]) -> list[str]:
        texts: list[str | None] = [None] * len(events)
        pending: list[tuple[int, dict[str, Any]]] = []
        batch_last: dict[tuple[str, Any], tuple[int, str]] = {}

        for i, ev in enumerate(events):
            key = _event_key(ev)
            sec = float(ev.get("t_ms") or 0)
            last = self._last.get(key) or batch_last.get(key)
            try:
                age_ms = sec - float(last[0]) if last else 1e18
            except (TypeError, ValueError):
                age_ms = 1e18
            if last and age_ms < self._min_gap_ms:
                self._deduped += 1
                texts[i] = last[1]
                self._prev = ev
                continue
            if self._calls >= self._max_calls or time.time() < _MODEL_COOLDOWN_UNTIL:
                self._fallbacks += 1
                texts[i] = self._fallback.generate(ev)
                self._prev = ev
                continue
            pending.append((i, ev))

        if pending:
            for _, ev in pending:
                scene = self._scene_for(ev)
                if scene:
                    ev["scene"] = scene
            started = time.perf_counter()
            recent = list(self._recent)
            try:
                timeout = self._timeout_s * max(1, len(pending))
                lines = self._executor.submit(
                    self._invoke_batch,
                    self._batch_prompt([ev for _, ev in pending], recent),
                    len(pending),
                ).result(timeout=timeout)
                self._calls += 1
                self._last_sec = time.perf_counter() - started
                logger.info(
                    "commentary LLM batch ok n=%d %.2fs -> %s",
                    len(pending), self._last_sec, (lines[0] if lines else "")[:30],
                )
            except FutureTimeout:
                lines = []
                self._fallbacks += len(pending)
                logger.warning("commentary LLM 批量超时（>%.0fs），整批回退模板句", timeout)
            except Exception as exc:  # noqa: BLE001 - 任何失败都要保住任务
                lines = []
                self._fallbacks += len(pending)
                if _quota_hit(exc):
                    _set_model_cooldown()
                logger.warning("commentary LLM 批量失败，整批回退模板句 err=%s", exc)

            for (i, ev), line in zip(pending, lines):
                texts[i] = line
                key = _event_key(ev)
                entry = (int(float(ev.get("t_ms") or 0)), line)
                self._last[key] = entry
                batch_last[key] = entry
                self._prev = ev
            for i, ev in pending:  # 模型少给的行用模板句补齐
                if texts[i] is None:
                    self._fallbacks += 1
                    texts[i] = self._fallback.generate(ev)
                    self._prev = ev

        produced = [t for t in texts if t]
        if produced:
            self._recent = produced[-2:]
        return [t or "" for t in texts]

    def close(self) -> None:
        if self._grabber is not None:
            self._grabber.close()
        self._executor.shutdown(wait=False)


def _set_model_cooldown() -> None:
    global _MODEL_COOLDOWN_UNTIL
    import time as _time

    _MODEL_COOLDOWN_UNTIL = _time.time() + _QUOTA_COOLDOWN_S
    logger.warning("检测到配额/限流错误，解说 LLM 冷却 %.0f 分钟（期间直接走模板句）", _QUOTA_COOLDOWN_S / 60)
