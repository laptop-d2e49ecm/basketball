from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.db import task_repo

router = APIRouter(tags=["task updates"])


@router.websocket("/ws/task/{task_id}")
async def task_updates(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    if task_repo.get_task(task_id) is None:
        await websocket.send_json({"type": "failed", "error": "任务不存在"})
        await websocket.close(code=1008)
        return

    last_id = 0
    try:
        while True:
            messages = task_repo.notifications_after(task_id, last_id)
            for message in messages:
                last_id = message.pop("id")
                await websocket.send_json(message)
                if message.get("type") in {"done", "failed"}:
                    await websocket.close()
                    return
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        return
