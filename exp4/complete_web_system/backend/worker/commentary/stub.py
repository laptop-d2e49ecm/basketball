from __future__ import annotations

from typing import Any

from worker.commentary.base import CommentaryService


class StubCommentaryService(CommentaryService):
    """Generate cautious Chinese captions from the current detector output."""

    def generate(self, event: dict[str, Any]) -> str:
        count = int(event.get("player_count", 0))
        if event.get("type") == "action":
            zh = str(event.get("action_zh") or event.get("action") or "动作")
            phrases = {
                "pass": "这一下，看起来是把球传了出去。",
                "dribble": "球还在手里，看起来是在运球。",
                "drive": "看持球人这一步，像是要往里突。",
                "shot_3p": "抬手了，看起来是一次三分尝试！",
                "shot_2p": "看这一下起手，像是准备两分出手。",
                "interfere_shot": "这一下，像是在干扰对方出手。",
                "screen": "留意无球队员，这一下像是掩护。",
                "rebound": "注意篮板，这一下像是在争球。",
                "block": "手伸起来了，看着像是要封盖！",
                "steal": "这一下伸手，像是想把球断下来。",
            }
            return phrases.get(event.get("action"), f"留意这个动作，看起来像是{zh}。")
        if event.get("type") == "player_cluster":
            return f"看这边，约有 {count} 名球员聚到了一块。"
        if event.get("type") == "group_direction_change":
            return "几名球员换了方向，往另一边跑了。"
        if count == 0:
            return "这会儿看不清球员的位置。"
        if event.get("type") == "player_count_change":
            return f"镜头里的人数有变化，这会儿能看到约 {count} 人。"
        return f"镜头里能看到约 {count} 名球员。"
