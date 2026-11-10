# -*- coding: utf-8 -*-
"""段4 基线：实验4 的 joblib 分类器 + 大模型零样本，各考 10 道题。

产物：exp5/eval/baseline.json（逐题作答 + 准确率），供三方对比表使用。
用法：backend\\.venv\\Scripts\\python.exe -X utf8 exp5/eval/baseline.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "exp4/complete_web_system/backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).parent))

import httpx  # noqa: E402
import joblib  # noqa: E402
from openai import OpenAI  # noqa: E402
from app.agent.providers import load_env  # noqa: E402
from prompt import build_prompt, parse_label  # noqa: E402

EXAM = REPO / "exp5/data/agent_eval_10.json"
CLF = BACKEND / "app/ml/text_action_clf.joblib"
OUT = REPO / "exp5/eval/baseline.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    items = json.loads(EXAM.read_text(encoding="utf-8"))
    clf = joblib.load(CLF)
    joblib_pred = clf.predict([x["input"] for x in items]).tolist()

    cfg = load_env()
    model = cfg.get("EXP5_LLM_MODEL", "deepseek-chat")
    client = OpenAI(
        base_url=cfg["EXP5_LLM_BASE_URL"],
        api_key=cfg["EXP5_LLM_API_KEY"],
        timeout=60,
        http_client=httpx.Client(trust_env=False, timeout=60),
    )

    rows = []
    for i, (item, jp) in enumerate(zip(items, joblib_pred), 1):
        prompt = build_prompt(item["input"])
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=16,
        )
        raw = (resp.choices[0].message.content or "").strip()
        pred = parse_label(raw)
        rows.append({
            "id": i,
            "gold": item["output"],
            "text": item["input"],
            "joblib_pred": jp,
            "zeroshot_raw": raw,
            "zeroshot_pred": pred,
        })
        print(f'{i:2d}. gold={item["output"]:<6} joblib={jp:<6} zero={pred or "?" :<6} raw={raw!r}')

    acc_j = sum(1 for r in rows if r["joblib_pred"] == r["gold"]) / len(rows)
    acc_z = sum(1 for r in rows if r["zeroshot_pred"] == r["gold"]) / len(rows)
    payload = {
        "model": model,
        "n": len(rows),
        "joblib_accuracy": round(acc_j, 3),
        "zeroshot_accuracy": round(acc_z, 3),
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\njoblib {acc_j:.0%} ({sum(1 for r in rows if r['joblib_pred']==r['gold'])}/{len(rows)})"
          f" | 零样本 {acc_z:.0%} ({sum(1 for r in rows if r['zeroshot_pred']==r['gold'])}/{len(rows)})")
    print(f"已存 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
