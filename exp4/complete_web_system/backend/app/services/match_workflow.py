from __future__ import annotations


def run_match(detector, text_classifier, image: bytes, text: str, conf: float = 0.25) -> dict:
    image_result = detector.api_detect(image, conf=conf)
    text_result = text_classifier.predict(text)

    is_court = image_result["player_count"] >= 1
    evidence: list[str] = []
    if is_court:
        confidence = _average_confidence(image_result)
        evidence.append(f"图像侧检测到 {image_result['player_count']} 名球员，平均置信度 {confidence:.2f}")
    else:
        evidence.append("图像侧未检出球员，可能不是比赛画面或画面较模糊")

    if text_result["is_basketball_text"]:
        evidence.append(f"文本侧判定为篮球赛事解说，类别为“{text_result['label']}”")
    else:
        evidence.append("文本侧判定为非篮球赛事文本")

    return {
        "match": is_court and text_result["is_basketball_text"],
        "image_side": {
            "is_court": is_court,
            "player_count": image_result["player_count"],
            "avg_conf": _average_confidence(image_result),
            "infer_ms": image_result["infer_ms"],
        },
        "text_side": {
            "label": text_result["label"],
            "is_basketball_text": text_result["is_basketball_text"],
            "confidence": text_result["confidence"],
        },
        "evidence": evidence,
        "total_ms": round(image_result["total_ms"] + text_result["infer_ms"], 2),
    }


def _average_confidence(result: dict) -> float:
    boxes = result["boxes"]
    if not boxes:
        return 0.0
    return round(sum(float(box["conf"]) for box in boxes) / len(boxes), 4)
