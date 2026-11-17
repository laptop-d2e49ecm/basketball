# -*- coding: utf-8 -*-
"""Agent 对话 API：POST /api/v1/agent/chat（任务书 5.4.1，契约 exp5/CONTRACT.md）。

- 统一信封 {code, result, msg}，错误码复用实验4 体系（400/404/500），新增 504（LLM 超时）；
- Agent 懒加载：首次请求时构建（缺 .env 配置不影响系统其他功能启动）；
- 会话断点续聊：session_id 存 SQLite（agent_sessions 表），首轮不传由后端新建；
- 逐轮日志落 backend/logs/agent.jsonl（用户查询 + 工具调用 + 耗时）。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.errors import ModelError, NotFoundError
from app.db import agent_sessions
from app.schemas.envelope import ApiEnvelope
from worker.commentary.llm import content_text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agent"])

_MS_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*ms")


class AgentChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=500)


def _provider_name() -> str:
    from app.agent.providers import load_env

    return load_env().get("EXP5_LLM_PROVIDER", "api")


def _get_agent(request: Request):
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        from app.agent.graph import build_agent

        try:
            agent = build_agent()
        except Exception as exc:  # noqa: BLE001 - 配置缺失/依赖问题转 500 信封
            raise ModelError(f"AI 服务未就绪：{exc}") from exc
        request.app.state.agent = agent
    return agent


def _history_to_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """存储格式（user/agent）转模型输入格式（user/assistant），工具过程不回传模型。

    content 经 content_text 归一：新中转可能把回复存成块列表，历史里残留的
    列表内容在这里提取纯文本，避免把块结构 repr 回传给模型。
    """
    messages = []
    for item in history:
        role = "user" if item.get("role") == "user" else "assistant"
        content = content_text(item.get("content", ""))
        if content:
            messages.append({"role": role, "content": content})
    return messages


def _trace_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """从 langgraph 结果消息提取工具调用轨迹（契约第 3 节 tool_calls 字段）。"""
    calls: list[dict[str, Any]] = []
    for msg in messages:
        if getattr(msg, "type", "") == "ai" and getattr(msg, "tool_calls", None):
            for call in msg.tool_calls:
                calls.append({"tool": call.get("name", ""), "args": call.get("args", {})})
    tool_results = [str(m.content) for m in messages if getattr(m, "type", "") == "tool"]
    for item, content in zip(calls, tool_results):
        item["status"] = "error" if content.startswith("工具调用失败") else "ok"
        item["result_summary"] = content[:200]
        matched = _MS_PATTERN.search(content)
        item["elapsed_ms"] = float(matched.group(1)) if matched else None
    return calls


def _write_log(session_id: str, user: str, trace: list[dict[str, Any]], elapsed_ms: int) -> None:
    from app.agent.providers import BACKEND_DIR

    log_dir = BACKEND_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session_id": session_id,
            "user": user,
            "tool_calls": trace,
            "elapsed_ms": elapsed_ms,
            "provider": _provider_name(),
        }
        with (log_dir / "agent.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 日志失败不影响对话


@router.post("/agent/chat", summary="AI 解说助手对话（实验5）", response_model=ApiEnvelope[dict[str, Any]])
def agent_chat(payload: AgentChatRequest, request: Request) -> ApiEnvelope[dict[str, Any]]:
    started = time.perf_counter()

    if payload.session_id:
        history = agent_sessions.load_history(payload.session_id)
        if history is None:
            raise NotFoundError("会话不存在，请去掉 session_id 重新开始对话")
        session_id = payload.session_id
    else:
        session_id = agent_sessions.new_session()
        history = []

    agent = _get_agent(request)
    messages = _history_to_messages(history) + [{"role": "user", "content": payload.message}]

    try:
        result = agent.invoke({"messages": messages})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent_chat LLM 调用失败 session=%s", session_id)
        text = f"{type(exc).__name__}: {exc}".lower()
        if "timeout" in text or "timed out" in text:
            raise HTTPException(status_code=504, detail="AI 响应超时，请重试") from exc
        if "rate" in text or "429" in text:
            raise HTTPException(
                status_code=429, detail="AI 服务调用过于频繁，请稍等几秒再试"
            ) from exc
        raise ModelError("AI 服务暂时不可用，请稍后重试") from exc

    final = content_text(result["messages"][-1].content).strip() or "（AI 未返回内容，请重试）"
    trace = _trace_from_messages(result["messages"])
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    agent_sessions.append_history(
        session_id,
        [
            {"role": "user", "content": payload.message},
            {"role": "agent", "content": final, "tool_calls": trace},
        ],
    )
    _write_log(session_id, payload.message, trace, elapsed_ms)

    return ApiEnvelope(
        result={
            "session_id": session_id,
            "agent": final,
            "tool_calls": trace,
            "elapsed_ms": elapsed_ms,
            "provider": _provider_name(),
        }
    )
