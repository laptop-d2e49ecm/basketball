from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

EVENTS_PER_SEGMENT = 20
UNSUPPORTED_CLAIMS = ("教练", "裁判", "球权", "外线", "篮下", "命中", "进球", "得分", "比分", "领先", "落后")
logger = logging.getLogger("basketball-narration")


def _events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    return sorted(rows, key=lambda row: int(row.get("t_ms", 0)))


def generate_narration(
    task_id: str,
    events_path: Path,
    *,
    agent_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """让 Agent 逐段查询同一任务的全部事件，形成连续解说稿。"""
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
        prompt = (
            f"请为视频任务 {task_id} 生成赛后中文解说。"
            f"必须先调用 query_video_events，参数 task_id={task_id}、"
            f"offset={offset}、limit={len(group)}，只依据工具返回的这段事件。"
            f"这是整场解说的一小段，正文严格控制在约 {target_chars} 个汉字，只挑最有代表性的1至2个事件，按时间顺序自然讲述，不要编号。"
            "不要罗列置信度和全部事件，不要提任务编号、工具、分页、事件总数或剩余条数。"
            "动作类别只是模型预测，请用‘疑似’或‘可能’表达；不能把出手说成命中。"
            "除非事件明确提供证据，不得推断球权归属、外线或篮下位置、攻防方、战术，也不得编造比分、球员姓名、球队、赛果。"
            "如果只有人数或站位事件，就如实描述场面，不要硬猜具体动作。只输出解说正文。"
        )
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
            text = str(getattr(messages[-1], "content", "") or "").strip()
            if not text:
                raise RuntimeError("Agent 未返回解说文本")
            unsupported = [phrase for phrase in UNSUPPORTED_CLAIMS if phrase in text]
            if not unsupported:
                break
            if attempt:
                raise RuntimeError("Agent 解说反复包含事件未支持的断言")
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
    try:
        result = generate_narration(task_id, events_path)
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
