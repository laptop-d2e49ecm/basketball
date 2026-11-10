# -*- coding: utf-8 -*-
"""段3 数据质量审计：分类器一致性 + 逐条复核辅助。

输出一份可读清单，供人工逐条判断；同时算出"标注 vs 分类器"一致率（报告可用）。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import joblib

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "exp5/data/agent_finetune_data.json"
CLF = REPO / "exp4/complete_web_system/backend/app/ml/text_action_clf.joblib"

RULES = [
    ("罚球", r"罚球|罚篮|两罚|罚中|罚丢|加罚|技术犯规罚"),
    ("犯规违例", r"犯规|违例|走步|二次运球|翻腕|吹罚|哨响|罚出|夺权|挑战|裁判"),
    ("暂停换人", r"暂停|换人|下场|替补|登场|轮换|首发|回到场上|挑战成功"),
    ("抢断", r"抢断|断球|切球|抢下球权"),
    ("盖帽", r"盖帽|封盖|大帽|扇出"),
    ("篮板", r"篮板|前场板|后场板|争抢篮板"),
    ("助攻传球", r"助攻|传球|传给|妙传|分球|击地|长传|手递手|送出"),
    ("投篮", r"投篮|出手|跳投|三分|3分|两分|2分|上篮|扣篮|抛投|补篮|勾手|后仰|干拔|命中|得分|打进|球进|空心|打铁|不中|偏出|绝杀|压哨"),
    ("比分局势", r"比分|领先|落后|追分|反超|打停|分差|拉开|迫近|咬住|胶着|战成|打成|领先优势|稳住"),
    ("阵容战术", r"战术|挡拆|掩护|落位|站位|阵型|联防|盯人|包夹|夹击|协防|换防"),
]


def rule_label(text: str) -> str:
    for label, pat in RULES:
        if re.search(pat, text):
            return label
    return "其他"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    items = json.loads(DATA.read_text(encoding="utf-8"))
    clf = joblib.load(CLF)

    cls = [x for x in items if "文本分析" in x["instruction"]]
    gens = [x for x in items if "解说员" in x["instruction"]]

    preds = clf.predict([x["input"] for x in cls]).tolist()
    agree = sum(1 for x, p in zip(cls, preds) if p == x["output"])

    print(f"分类题 {len(cls)} 条；标注 vs 分类器一致 {agree}/{len(cls)} = {agree/len(cls):.1%}")
    print("\n=== 分类题逐条（标注 | 分类器 | 原句）===")
    for i, (x, p) in enumerate(zip(cls, preds), 1):
        flag = "" if p == x["output"] else "  <<< 不一致"
        print(f"{i:2d}. [{x['output']}] clf=[{p}] {x['input']}{flag}")

    print("\n=== 生成题（事件类型 → 解说句的规则标签）===")
    mismatch = 0
    for i, x in enumerate(gens, 1):
        m = re.match(r"事件：(.+?)；", x["input"])
        event = m.group(1) if m else "?"
        # 事件细节里带动作词，取细节首个动作词判断大类
        guessed = rule_label(event)
        real = rule_label(x["output"])
        if guessed != "其他" and real != "其他" and guessed != real:
            mismatch += 1
            print(f"{i:2d}. 事件[{event}]→{guessed} | 解说句→{real}  <<< 语义可能不符：{x['output']}")
    print(f"生成题疑似不符：{mismatch}/{len(gens)}")

    print("\n=== 分布 ===")
    print("分类题标签:", dict(Counter(x["output"] for x in cls)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
