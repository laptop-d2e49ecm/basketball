# -*- coding: utf-8 -*-
"""动作识别线的类别契约（18 类 MultiSports 原始标注 → 13 动作类 + 背景）。

长尾归并原则（实例数见 events.csv）：
  - pass-inbound(160) → pass；off/def rebound(288) → rebound；
    pass/dribble steal(75) → steal —— 语义同族、长尾合并；
  - jump ball(18)、save(5) 直接丢弃（合计 23 实例，无训练价值）；
  - _none 为背景类：来自无任何 tube 覆盖帧上的球员框，部署推理的"无动作"出口。

本文件是唯一事实来源：build_clips.py / train_action.py / export_onnx.py 引用它，
worker 运行时读 build 产出的 meta.json（内含同样的顺序）。
"""

from __future__ import annotations

# 原始 MultiSports 动作名 → 归并后类别名
CLASS_MAP: dict[str, str] = {
    "basketball pass": "pass",
    "basketball pass-inbound": "pass",
    "basketball dribble": "dribble",
    "basketball 2-point shot": "shot_2p",
    "basketball 3-point shot": "shot_3p",
    "basketball interfere shot": "interfere_shot",
    "basketball drive": "drive",
    "basketball screen": "screen",
    "basketball pick-and-roll defensive": "pick_roll_def",
    "basketball defensive rebound": "rebound",
    "basketball offensive rebound": "rebound",
    "basketball sag": "sag",
    "basketball free throw": "free_throw",
    "basketball pass steal": "steal",
    "basketball dribble steal": "steal",
    "basketball block": "block",
    # 丢弃：basketball jump ball / basketball save（不写入 CLASS_MAP 即被过滤）
}

BACKGROUND_CLASS = "_none"

# 顺序即类别索引（背景放最后，方便 worker 过滤）
CLASSES: list[str] = [
    "pass",
    "dribble",
    "shot_2p",
    "shot_3p",
    "interfere_shot",
    "drive",
    "screen",
    "pick_roll_def",
    "rebound",
    "sag",
    "free_throw",
    "steal",
    "block",
    BACKGROUND_CLASS,
]

# 中文标签（解说文案用）
ZH_NAMES: dict[str, str] = {
    "pass": "传球",
    "dribble": "运球",
    "shot_2p": "两分出手",
    "shot_3p": "三分出手",
    "interfere_shot": "投篮干扰",
    "drive": "持球突破",
    "screen": "掩护",
    "pick_roll_def": "防守挡拆",
    "rebound": "篮板拼抢",
    "sag": "收缩防守",
    "free_throw": "罚球",
    "steal": "抢断",
    "block": "盖帽",
    BACKGROUND_CLASS: "无动作",
}

CLASS_TO_IDX: dict[str, int] = {name: idx for idx, name in enumerate(CLASSES)}


def meta() -> dict:
    """写入数据集 meta.json 的类别信息（训练/导出/部署三方共用）。"""
    return {
        "classes": CLASSES,
        "class_to_idx": CLASS_TO_IDX,
        "zh_names": ZH_NAMES,
        "background_class": BACKGROUND_CLASS,
        "raw_to_class": CLASS_MAP,
    }
