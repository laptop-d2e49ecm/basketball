from __future__ import annotations

import json
import logging
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from worker.commentary.llm import content_text

EVENTS_PER_SEGMENT = 20
# 硬禁词：检测与画面事实永远无法支撑的断言（未检测教练/裁判；命中与否是结果判断）
HARD_CLAIMS = ("教练", "裁判", "命中", "进球")
# 比分类禁词：用户上传时填写了比分（两边都有）才解禁
SCORE_CLAIMS = ("得分", "比分", "领先", "落后")
# 画面证据类禁词：本段事件的画面观察出现对应证据才解禁
SCENE_CLAIMS = {"外线": ("外线", "三分线"), "篮下": ("篮下",), "球权": ("持球", "球在", "球位于")}
logger = logging.getLogger("basketball-narration")


def _events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return sorted(rows, key=lambda row: int(row.get("t_ms", 0)))


def _user_facts(context: dict[str, Any] | None) -> str:
    """用户填写的对阵与比分类事实行；空值逐项兜底（缺哪项不写哪项），全空返回空串。"""
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
    return "用户提供的对阵与比分（视为可信事实，其中给出的队名和比分可以直接使用）：" + "，".join(parts) + "。"


def _has_user_score(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    return bool(
        str(context.get("score1") or "").strip() and str(context.get("score2") or "").strip()
    )


def _effective_bans(group: list[dict[str, Any]], user_score: bool) -> tuple[str, ...]:
    """按事实源分层生成禁词：画面观察有证据、用户给了比分的词解禁。"""
    bans = list(HARD_CLAIMS)
    if not user_score:
        bans.extend(SCORE_CLAIMS)
    scene_text = "".join(str(row.get("scene") or "") for row in group)
    bans.extend(
        word
        for word, evidences in SCENE_CLAIMS.items()
        if not any(evidence in scene_text for evidence in evidences)
    )
    return tuple(bans)


def _sanitize(text: str, banned: tuple[str, ...]) -> str:
    """按句剔除含禁词的句子；全部被剔时返回空串，由调用方退回中性事实句。"""
    sentences = [s for s in re.split(r"(?<=[。！？!?])", text) if s.strip()]
    kept = [s for s in sentences if not any(word in s for word in banned)]
    return "".join(kept)


def generate_narration(
    task_id: str,
    events_path: Path,
    *,
    agent_factory: Callable[[], Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """让 Agent 逐段查询同一任务的全部事件，形成连续解说稿。

    context 为任务元数据（team1/team2/score1/score2，均可为空）：有值时作为
    用户事实注入提示词，比分类禁词同步解禁；空值逐项兜底。
    """
    events = _events(events_path)
    base: dict[str, Any] = {
        "task_id": task_id,
        "event_count": len(events),
        "source": "agent",
        "created_at": datetime.now(UTC).isoformat(),
        "sections": [],
        "tool_calls": [],
        "text": "",
        "error": None,
    }
    if not events:
        return {**base, "status": "empty"}

    user_facts = _user_facts(context)
    if agent_factory is None:
        from app.agent.graph import build_agent

        agent_factory = build_agent
    agent = agent_factory()
    previous_tail = ""
    duration_seconds = max(1, (int(events[-1].get("t_ms", 0)) - int(events[0].get("t_ms", 0))) / 1000)
    section_count = math.ceil(len(events) / EVENTS_PER_SEGMENT)
    target_chars = max(30, min(90, round(duration_seconds * 4 / section_count)))
    for offset in range(0, len(events), EVENTS_PER_SEGMENT):
        group = events[offset:offset + EVENTS_PER_SEGMENT]
        banned = _effective_bans(group, _has_user_score(context))
        prompt = (
            f"请为视频任务 {task_id} 生成赛后中文解说。"
            f"必须先调用 query_video_events，参数 task_id={task_id}、"
            f"offset={offset}、limit={len(group)}，只依据工具返回的这段事件。"
            f"这是整场解说的一小段，正文严格控制在约 {target_chars} 个汉字，只挑最有代表性的1至2个事件，按时间顺序自然讲述，不要编号。"
            "不要罗列置信度和全部事件，不要提任务编号、工具、分页、事件总数或剩余条数。"
            "动作类别只是模型预测，请用'疑似'或'可能'表达；不能把出手说成命中。"
            "不得编造攻防战术、球员姓名、球队、赛果；"
            "外线、篮下、球权只在事件的画面观察明确提及时可以写；"
            "比分、得分、领先、落后只在用户提供了比分时可以写。"
            "如果只有人数或站位事件，就如实描述场面，不要硬猜具体动作。只输出解说正文。"
        )
        if user_facts:
            prompt += user_facts
            if offset == 0:
                prompt += "这是整场解说的开场段：请在本段自然提到对阵双方，如有比分也带到一次。"
            else:
                prompt += "后续段落可在合适处自然带到队名或比分，不必强求。"
        if previous_tail:
            prompt += f"上一段解说结尾：{previous_tail}。请自然衔接，不要重复。"
        for attempt in range(2):
            result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
            messages = result.get("messages", [])
            calls = [
                call
                for message in messages
                for call in (getattr(message, "tool_calls", None) or [])
                if call.get("name") == "query_video_events"
            ]
            if not any(
                str(call.get("args", {}).get("task_id", "")).strip() == task_id
                and int(call.get("args", {}).get("offset", 0)) == offset
                and int(call.get("args", {}).get("limit", 20)) == len(group)
                for call in calls
            ):
                raise RuntimeError(f"Agent 未查询任务 {task_id} 的第 {offset + 1} 段事件")
            tool_messages = [m for m in messages if getattr(m, "type", "") == "tool"]
            if not any(
                f"任务 {task_id}" in str(message.content) and "的关键事件" in str(message.content)
                for message in tool_messages
            ):
                raise RuntimeError("视频事件查询工具未成功返回")
            base["tool_calls"].extend(
                {"name": "query_video_events", "args": call.get("args", {})} for call in calls
            )
            text = content_text(getattr(messages[-1], "content", "") or "").strip()
            if not text:
                raise RuntimeError("Agent 未返回解说文本")
            unsupported = [phrase for phrase in banned if phrase in text]
            if not unsupported:
                break
            if attempt:
                # 两稿仍有禁词：按句剔除兜底，绝不让整篇解说因个别断言失败
                text = _sanitize(text, tuple(unsupported)) or (
                    f"第 {int(group[0].get('t_ms', 0)) // 1000} 秒前后，画面共有 {len(group)} 条事件。"
                )
                logger.warning(
                    "解说第 %d 段仍含未支持断言，已按句剔除兜底", offset // EVENTS_PER_SEGMENT + 1
                )
                break
            prompt += "上一稿包含没有事件证据的词语（" + "、".join(unsupported) + "），请重新查询事件并改写，避免这些词。"
        base["sections"].append({
            "start_ms": int(group[0].get("t_ms", 0)),
            "end_ms": int(group[-1].get("t_ms", 0)),
            "event_count": len(group),
            "text": text,
        })
        previous_tail = text[-160:]
    base["text"] = "\n\n".join(section["text"] for section in base["sections"])
    base["status"] = "ready"
    return base


def write_narration(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run_task_narration(task_id: str, events_path: Path) -> dict[str, Any]:
    """解说失败时仍保留视频分析结果，并将可重试状态写入文件。"""
    context: dict[str, Any] = {}
    try:
        from app.db import task_repo

        row = task_repo.get_task(task_id)
        if row:
            context = dict(row.get("metadata") or {})
    except Exception:  # noqa: BLE001 - 元数据读不到只影响注入，不影响解说
        logger.warning("读取任务元数据失败，本篇解说不注入对阵与比分：%s", task_id)
    try:
        result = generate_narration(task_id, events_path, context=context)
    except Exception as exc:  # 外部模型故障不应使检测结果丢失
        logger.exception("整场 Agent 解说生成失败：%s", task_id)
        if "key 未配置" in str(exc):
            error = "请先在后端 .env 中配置大模型密钥，再点击重新生成解说。"
        elif isinstance(exc, (ImportError, ModuleNotFoundError)):
            error = "AI 解说依赖尚未安装，请安装后端 requirements.txt 后重试。"
        else:
            error = "AI 解说暂不可用，请检查后端日志并稍后重试。"
        try:
            event_count = len(_events(events_path))
        except (OSError, ValueError, json.JSONDecodeError):
            event_count = 0
        result = {
            "task_id": task_id, "status": "failed", "source": "agent",
            "event_count": event_count, "created_at": datetime.now(UTC).isoformat(),
            "sections": [], "tool_calls": [], "text": "",
            "error": error,
        }
    write_narration(events_path.parent / "narration.json", result)
    return result
