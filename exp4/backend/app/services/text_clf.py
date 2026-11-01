"""解说文本动作分类服务（实验 1 语料弱监督训练，pipeline 见 train_text_clf.py）。"""
from __future__ import annotations

import json
import time
from pathlib import Path

import joblib

from ..core.config import DOMAIN_CONF_THR, TEXT_META, TEXT_MODEL
from ..core.errors import ModelError


def _softmax(z):
    import numpy as np
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


class TextClassifier:
    def __init__(self, model_path: Path = TEXT_MODEL, meta_path: Path = TEXT_META):
        if not model_path.exists():
            raise ModelError(f"文本分类模型缺失: {model_path.name}，请先运行 train_text_clf.py")
        self.pipe = joblib.load(model_path)
        self.meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        self.classes = list(self.pipe.classes_)
        self.domain_thr = float(self.meta.get("domain_conf_thr", DOMAIN_CONF_THR))
        # 域判定规则优先（短文本决策值低，如"换人了"；规则命中即域内，模型阈值兜底）
        import re
        self._rules = [re.compile(r["pattern"]) for r in self.meta.get("rules", [])]

    def _rule_hit(self, text: str) -> bool:
        return any(rx.search(text) for rx in self._rules)

    def predict(self, text: str) -> dict:
        t0 = time.perf_counter()
        try:
            dec = self.pipe.decision_function([text])[0]
        except Exception as e:  # noqa: BLE001
            raise ModelError(f"文本分类失败: {e}") from e
        probs = _softmax(dec)
        order = probs.argsort()[::-1]
        top3 = [{"label": self.classes[i], "prob": round(float(probs[i]), 4)} for i in order[:3]]
        best = int(order[0])
        rule_hit = self._rule_hit(text)
        is_domain = rule_hit or float(probs[best]) >= self.domain_thr
        return {
            "label": self.classes[best] if is_domain else "非篮球赛事文本",
            "is_basketball_text": bool(is_domain),
            "confidence": round(float(probs[best]), 4),
            "top3": top3,
            "chars": len(text),
            "infer_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
