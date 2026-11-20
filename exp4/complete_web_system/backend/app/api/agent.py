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
import io
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, File, Form, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from app.core.config import settings
from pydantic import BaseModel, Field

from app.core.errors import ModelError, NotFoundError
from app.db import agent_sessions, task_repo
from app.schemas.envelope import ApiEnvelope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agent"])

_MS_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*ms")


class AgentChatRequest(BaseModel):
    session_id: str | None = None
    task_id: str | None = None
    message: str = Field(min_length=1, max_length=500)
    image_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


def _chat_image_path(task_id: str, image_id: str) -> Path:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", task_id) or not re.fullmatch(r"[a-f0-9]{32}", image_id):
        raise HTTPException(status_code=400, detail="图片标识无效")
    if task_repo.get_task(task_id) is None:
        raise NotFoundError("视频任务不存在")
    root = settings.runs_dir.resolve()
    path = (root / task_id / "chat_images" / f"{image_id}.jpg").resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="图片目录无效")
    return path


def _image_record(task_id: str, image_id: str) -> dict[str, str]:
    path = _chat_image_path(task_id, image_id)
    if not path.is_file():
        raise NotFoundError("图片不存在，请重新上传或选取")
    return {"id": image_id, "url": f"/api/v1/agent/images/{task_id}/{image_id}"}


@router.post("/agent/images", response_model=ApiEnvelope[dict[str, Any]])
def upload_chat_image(task_id: str = Form(...), file: UploadFile = File(...)) -> ApiEnvelope[dict[str, Any]]:
    image_id = uuid.uuid4().hex
    path = _chat_image_path(task_id, image_id)
    try:
        data = file.file.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="图片不能超过 10 MB")
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(status_code=400, detail="请上传 JPG、PNG 或 WebP 图片")
                if source.width * source.height > 20_000_000:
                    raise HTTPException(status_code=400, detail="图片像素过大，请缩小后上传")
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((2560, 2560))
                path.parent.mkdir(parents=True, exist_ok=True)
                image.save(path, format="JPEG", quality=92)
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="图片无法读取，请换一张图片") from exc
        return ApiEnvelope(result={**_image_record(task_id, image_id), "name": Path(file.filename or "图片").name})
    finally:
        file.file.close()


@router.get("/agent/images/{task_id}/{image_id}")
def get_chat_image(task_id: str, image_id: str) -> FileResponse:
    _image_record(task_id, image_id)
    return FileResponse(_chat_image_path(task_id, image_id), media_type="image/jpeg")


@router.get("/agent/sessions", response_model=ApiEnvelope[list[dict[str, Any]]])
def list_agent_sessions(task_id: str | None = None) -> ApiEnvelope[list[dict[str, Any]]]:
    return ApiEnvelope(result=agent_sessions.list_sessions(task_id))


@router.get("/agent/sessions/{session_id}", response_model=ApiEnvelope[dict[str, Any]])
def get_agent_session(session_id: str) -> ApiEnvelope[dict[str, Any]]:
    session = agent_sessions.get_session(session_id)
    if session is None:
        raise NotFoundError("会话不存在")
    return ApiEnvelope(result=session)


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


def _history_to_messages(history: list[dict[str, Any]], task_id: str | None = None) -> list[dict[str, str]]:
    """存储格式（user/agent）转模型输入格式（user/assistant），工具过程不回传模型。"""
    messages = []
    for item in history:
        role = "user" if item.get("role") == "user" else "assistant"
        content = str(item.get("content", ""))
        image = item.get("image")
        if role == "user" and task_id and isinstance(image, dict):
            try:
                path = _chat_image_path(task_id, str(image.get("id", "")))
                if path.is_file():
                    content += f"\n本轮附图的工具路径：{path}。图片问题请使用 player_detect 或 image_text_match。"
            except (HTTPException, NotFoundError):
                pass
        if content:
            messages.append({"role": role, "content": content})
    return messages


def _trace_from_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """从 langgraph 结果消息提取工具调用轨迹（契约第 3 节 tool_calls 字段）。"""
    calls: list[dict[str, Any]] = []
    call_ids: list[str | None] = []
    for msg in messages:
        if getattr(msg, "type", "") == "ai" and getattr(msg, "tool_calls", None):
            for call in msg.tool_calls:
                calls.append({"tool": call.get("name", ""), "args": call.get("args", {})})
                call_ids.append(call.get("id"))
    tool_results = [m for m in messages if getattr(m, "type", "") == "tool"]
    has_result_ids = any(getattr(m, "tool_call_id", None) for m in tool_results)
    for index, (item, call_id) in enumerate(zip(calls, call_ids)):
        # Parallel tool results may arrive in a different order from the calls.
        if has_result_ids and call_id:
            result = next((m for m in tool_results if getattr(m, "tool_call_id", None) == call_id), None)
        else:
            result = tool_results[index] if index < len(tool_results) else None
        content = str(result.content) if result is not None else "工具未返回结果"
        item["status"] = "error" if result is None or content.startswith("工具调用失败") else "ok"
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

    if payload.task_id and task_repo.get_task(payload.task_id) is None:
        raise NotFoundError("视频任务不存在")

    if payload.session_id:
        session = agent_sessions.get_session(payload.session_id)
        if session is None:
            raise NotFoundError("会话不存在，请去掉 session_id 重新开始对话")
        if payload.task_id and session["task_id"] != payload.task_id:
            raise HTTPException(status_code=409, detail="会话与视频任务不匹配")
        history = session["history"]
        session_id = payload.session_id
        task_id = session["task_id"]
    else:
        task_id = payload.task_id
        session_id = agent_sessions.new_session(task_id)
        history = []

    image = None
    image_context = ""
    if payload.image_id:
        if not task_id:
            raise HTTPException(status_code=400, detail="图片需关联当前视频任务")
        image = _image_record(task_id, payload.image_id)
        image_context = f"\n用户附图的工具路径：{_chat_image_path(task_id, payload.image_id)}。询问图片人数时调用 player_detect，询问图文是否匹配时调用 image_text_match，image_path 使用此路径。不要将视频事件当成这张图片的检测结果。"
    agent = _get_agent(request)
    task_context = f"当前视频任务编号为 {task_id}。询问该视频事件时，先调用 query_video_events 并以查询结果为依据。\n" if task_id else ""
    messages = _history_to_messages(history, task_id) + [{"role": "user", "content": task_context + payload.message + image_context}]

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

    final = str(result["messages"][-1].content)
    trace = _trace_from_messages(result["messages"])
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    agent_sessions.append_history(
        session_id,
        [
            {"role": "user", "content": payload.message, **({"image": image} if image else {})},
            {"role": "agent", "content": final, "tool_calls": trace},
        ],
    )
    _write_log(session_id, payload.message, trace, elapsed_ms)

    return ApiEnvelope(
        result={
            "session_id": session_id,
            "task_id": task_id,
            "agent": final,
            "tool_calls": trace,
            "elapsed_ms": elapsed_ms,
            "provider": _provider_name(),
        }
    )
