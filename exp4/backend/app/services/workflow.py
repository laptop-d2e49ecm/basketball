"""图文匹配工作流（任务书 4.2.3）：图像检测 API 与文本分类 API 的串联编排。

流程：前端上传图像+文本 → 先图像检测（是否比赛画面/球员数）→ 再文本分类
（是否篮球赛事文本/动作类别）→ 一致性判定 → 返回双方证据。
"""
from __future__ import annotations

from ..services.detector import Detector
from ..services.text_clf import TextClassifier


def run_match(detector: Detector, text_clf: TextClassifier, image: bytes,
              text: str, conf: float | None = None) -> dict:
    det = detector.api_detect(image, conf=conf)
    txt = text_clf.predict(text)

    is_court = det["player_count"] >= 1
    evidence: list[str] = []
    if is_court:
        evidence.append(f"图像侧：检测到 {det['player_count']} 名球员（实验3 INT8 模型，"
                        f"平均置信度 {det.get('avg_conf', _avg_conf(det)):.2f}），判定为篮球比赛画面")
    else:
        evidence.append("图像侧：未检出球员，判定为非比赛画面（或画面过于模糊）")
    if txt["is_basketball_text"]:
        evidence.append(f"文本侧：判定为篮球赛事文本，动作类别「{txt['label']}」"
                        f"（置信度 {txt['confidence']:.2f}）")
    else:
        evidence.append(f"文本侧：置信度不足（{txt['confidence']:.2f} < {text_clf.domain_thr}），"
                        "判定为非篮球赛事文本")

    match = is_court and txt["is_basketball_text"]
    return {
        "match": match,
        "image_side": {
            "is_court": is_court,
            "player_count": det["player_count"],
            "avg_conf": _avg_conf(det),
            "infer_ms": det["infer_ms"],
        },
        "text_side": {
            "label": txt["label"],
            "is_basketball_text": txt["is_basketball_text"],
            "confidence": txt["confidence"],
        },
        "evidence": evidence,
        "total_ms": round(det["total_ms"] + txt["infer_ms"], 2),
    }


def _avg_conf(det: dict) -> float:
    if not det["boxes"]:
        return 0.0
    return round(sum(b["conf"] for b in det["boxes"]) / len(det["boxes"]), 4)
