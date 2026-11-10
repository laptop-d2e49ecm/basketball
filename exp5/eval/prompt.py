# -*- coding: utf-8 -*-
"""训练与评测共用的提示词（唯一来源，保证三方对比时"变量只有上没上过课"）。

训练数据里的 `instruction` 字段与这里 `INSTRUCTION` 必须逐字一致，
`exp5/data/audit_data.py` 会做一致性断言。
"""
from __future__ import annotations

INSTRUCTION = (
    "判断下面这句篮球解说的动作类别，只输出类别名，不要解释。"
    "可选类别：罚球、犯规违例、暂停换人、抢断、盖帽、篮板、助攻传球、投篮、比分局势、阵容战术"
)

LABELS = ["罚球", "犯规违例", "暂停换人", "抢断", "盖帽", "篮板", "助攻传球", "投篮", "比分局势", "阵容战术"]


def build_prompt(text: str) -> str:
    """与训练时拼给模型的 user 内容完全一致。"""
    return f"{INSTRUCTION}\n解说：{text}\n类别："


def parse_label(answer: str) -> str:
    """从模型输出里取类别名：先精确匹配，再取最先出现的类别；无法判定返回空串。

    只做"取第一个出现的合法类别"，不做模糊纠错——纠错会把答错算成答对。
    """
    if not answer:
        return ""
    clean = answer.strip().strip("。.！!？?\"'` \n")
    if clean in LABELS:
        return clean
    hits = [(clean.find(lb), lb) for lb in LABELS if lb in clean]
    if not hits:
        return ""
    hits.sort()
    return hits[0][1]
