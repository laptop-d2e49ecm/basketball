from __future__ import annotations

import re
from typing import Any

HARD_CLAIMS = ("教练", "裁判", "得分", "命中", "进球", "绝杀", "反超", "打进", "投进", "球进了", "得手", "取胜", "获胜")
# 比分类禁词：用户上传时填写了比分（两边都有）才解禁
SCORE_CLAIMS = ("比分", "领先", "落后")
# 画面证据类禁词：本段事件的画面观察出现对应证据才解禁
SCENE_CLAIMS = {"外线": ("外线", "三分线"), "篮下": ("篮下",), "球权": ("持球", "球在", "球位于")}


def user_facts(context: dict[str, Any] | None) -> str:
    """用户填写的对阵与比分类事实行；空值逐项兜底（缺哪项不写哪项），全空返回空串。"""
    if not isinstance(context, dict):
        return ""
    team1 = str(context.get("team1") or "").strip()
    team2 = str(context.get("team2") or "").strip()
    score = _score(context)
    parts: list[str] = []
    if team1:
        parts.append(f"主队{team1}")
    if team2:
        parts.append(f"客队{team2}")
    if score:
        parts.append(f"比分 {score[0]}:{score[1]}")
    if not parts:
        return ""
    return "用户填写的比赛资料（仅可引用已列出的值）：" + "，".join(parts) + "。"


def _score(context: dict[str, Any] | None) -> tuple[int, int] | None:
    values = [(context or {}).get(key) for key in ("score1", "score2")]
    if all(v is not None and re.fullmatch(r"[0-9]{1,3}", str(v).strip()) for v in values):
        return int(values[0]), int(values[1])
    return None


def unsupported(text: str, group: list[dict[str, Any]], context: dict[str, Any] | None) -> list[str]:
    score = _score(context)
    terms = [term for term in _effective_bans(group, score is not None) if term in text]
    for match in re.finditer(r"(?<![0-9])([0-9]{1,3})\s*[:：比]\s*([0-9]{1,3})(?![0-9])", text):
        if tuple(map(int, match.groups())) != score:
            terms.append(match.group())
    # Only an explicitly observed jersey number can be spoken as a player number.
    scene = " ".join(str(row.get("scene") or "") for row in group)
    for match in re.finditer(r"(?<![0-9])([0-9]{1,3})\s*号", text):
        number = match.group(1)
        if not re.search(r"(?<![0-9])" + re.escape(number) + r"\s*号", scene):
            terms.append(match.group())
    return terms


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


def sanitize(text: str, banned: tuple[str, ...]) -> str:
    """按句剔除含禁词的句子；全部被剔时返回空串，由调用方退回中性事实句。"""
    sentences = [s for s in re.split(r"(?<=[。！？!?])", text) if s.strip()]
    kept = [s for s in sentences if not any(word in s for word in banned)]
    return "".join(kept)
