from __future__ import annotations

from typing import Any

from worker.commentary.base import CommentaryService


class StubCommentaryService(CommentaryService):
    """Generate cautious Chinese captions from the current detector output."""

    def generate(self, event: dict[str, Any]) -> str:
        count = int(event.get("player_count", 0))
        if event.get("type") == "action":
            zh = str(event.get("action_zh") or event.get("action") or "动作")
            sec = (event.get("t_ms") or 0) / 1000
            conf = event.get("conf")
            tail = f"（模型置信度 {conf:.0%}）" if isinstance(conf, float) else ""
            return f"第 {sec:.1f} 秒，有球员{zh}{tail}。"
        if event.get("type") == "player_cluster":
            return f"画面局部出现约 {count} 名球员聚集。"
        if event.get("type") == "group_direction_change":
            return "画面中球员群体的整体移动方向出现变化。"
        if count == 0:
            return "当前画面暂未检测到球员，可能存在遮挡或漏检。"
        if event.get("type") == "player_count_change":
            return f"画面可见球员人数有所变化，目前检测到约 {count} 名球员。"
        return f"画面中检测到约 {count} 名球员。"
