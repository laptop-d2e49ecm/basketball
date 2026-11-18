from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from worker.commentary.evidence import sanitize, unsupported, user_facts
from worker.commentary.llm import content_text
from worker.commentary.stub import StubCommentaryService

EVENTS_PER_SEGMENT = 20
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

    facts = user_facts(context)
    if agent_factory is None:
        from app.agent.graph import build_agent

        agent_factory = build_agent
    agent = agent_factory()
    previous_tail = ""
    duration_ms = max(
        int(events[-1].get("t_ms", 0)) + 1000,
        round(float((context or {}).get("video_duration_seconds") or 0) * 1000),
    )
    for offset in range(0, len(events), EVENTS_PER_SEGMENT):
        group = events[offset:offset + EVENTS_PER_SEGMENT]
        start_ms = 0 if offset == 0 else int(group[0].get("t_ms", 0))
        next_offset = offset + len(group)
        end_ms = int(events[next_offset].get("t_ms", 0)) if next_offset < len(events) else duration_ms
        segment_seconds = max(1, (end_ms - start_ms) / 1000)
        target_chars = max(15, round(segment_seconds * 5.5))
        prompt = (
            f"请为视频任务 {task_id} 生成跟随视频播放的中文现场解说。"
            f"必须先调用 query_video_events，参数 task_id={task_id}、"
            f"offset={offset}、limit={len(group)}，只依据工具返回的这段事件。"
            f"本段覆盖视频 {start_ms / 1000:.1f} 至 {end_ms / 1000:.1f} 秒，共 {segment_seconds:.1f} 秒。"
            f"按云健正常解说语速，正文目标约 {target_chars} 个汉字（上下浮动10%），让朗读尽量覆盖本段时长。"
            "围绕事件中有依据的动作过程、持球人的移动、传接衔接和画面变化展开，使用多句长短结合的口语，避免只用一两句话概括后留下大段空白。"
            "先交代动作，再补充工具中实际提供的细节，最后自然衔接下一句；禁止把同一个事实换说法重复凑时长。"
            "若画面证据不足，允许缩短；不能为填满时间虚构动作、结果或情绪。"
            "不要罗列置信度和全部事件，不要提任务编号、工具、分页、事件总数或剩余条数。"
            "像坐在场边陪观众看球：从球怎么走、球员怎么动讲起。有关联的动作用一句话接起来，同时出现的动作不要硬写成先后。\n画面平稳就平叙，确有亮点时可用一个短句提气。"
            "用“看起来像”“似乎要”自然表达不确定，一组动作可共用一个判断，不要每句都说“疑似”。不要用“模型识别到”“节奏明显加快”或“让我们拭目以待”等套话。不得编造攻防战术、球员姓名、球队、赛果，不能把出手说成命中；可以引用画面观察明确关联到动作主体的球队文字、球衣颜色和球衣号码，如“USA白衣26号”，号码看不清就用“白衣球员”。用户仅填写对阵不能据此猜某球员属于哪队。track_id是内部跟踪编号，绝不是球衣号码，禁止把它读成几号球员；"
            "外线、篮下、球权只在事件的画面观察明确提及时可以写；"
            "只能引用用户填写的原比分，不能据此推断某个事件得分、实时比分或赛果。"
            "把球或持球人当主语，挑一条线讲，不要把运球、传球、突破并排报菜名。有动作时不用从人数开头或用人数收尾。仅有人数时说镜头里看见几人，不能说正式上场几人。比如事实只有传球和随后一次疑似突破，可以说“球传出来了。接下来这一步，看着像是要往里突。”示例只借语气，无对应事实不引用。只输出可直接朗读的正文。"
        )
        if facts:
            prompt += facts
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
            violations = unsupported(text, group, context)
            if not violations:
                break
            if attempt:
                # 两稿仍有禁词：按句剔除兜底，绝不让整篇解说因个别断言失败
                text = sanitize(text, tuple(violations)) or StubCommentaryService().generate(group[0])
                logger.warning(
                    "解说第 %d 段仍含未支持断言，已按句剔除兜底", offset // EVENTS_PER_SEGMENT + 1
                )
                break
            prompt += "上一稿包含没有事件证据的词语（" + "、".join(violations) + "），请重新查询事件并改写，避免这些词。"
        base["sections"].append({
            "start_ms": start_ms,
            "end_ms": end_ms,
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
