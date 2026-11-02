from __future__ import annotations

import json
import re
import time
from pathlib import Path

import joblib
import numpy as np

from app.core.errors import ModelError


class TextClassifier:
    def __init__(self, model_path: Path, meta_path: Path) -> None:
        if not model_path.is_file():
            raise ModelError(f"文本分类模型文件缺失：{model_path.name}")
        try:
            self.pipeline = joblib.load(model_path)
        except Exception as exc:
            raise ModelError("文本分类模型无法加载，请确认模型文件与 scikit-learn 版本匹配") from exc
        self.meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        self.classes = list(self.pipeline.classes_)
        self.domain_threshold = float(self.meta.get("domain_conf_thr", 0.5))
        self.rules = [re.compile(item["pattern"]) for item in self.meta.get("rules", [])]

    def predict(self, text: str) -> dict:
        started = time.perf_counter()
        try:
            decision = np.asarray(self.pipeline.decision_function([text]))[0]
            if decision.ndim == 0:
                decision = np.array([-decision, decision])
            shifted = decision - decision.max()
            probabilities = np.exp(shifted)
            probabilities /= probabilities.sum()
        except Exception as exc:
            raise ModelError("文本分类失败") from exc

        order = probabilities.argsort()[::-1]
        best_index = int(order[0])
        confidence = float(probabilities[best_index])
        in_domain = confidence >= self.domain_threshold or any(rule.search(text) for rule in self.rules)
        return {
            "label": self.classes[best_index] if in_domain else "非篮球赛事文本",
            "is_basketball_text": bool(in_domain),
            "confidence": round(confidence, 4),
            "top3": [
                {"label": self.classes[int(index)], "prob": round(float(probabilities[index]), 4)}
                for index in order[:3]
            ],
            "chars": len(text),
            "infer_ms": round((time.perf_counter() - started) * 1000, 2),
        }
