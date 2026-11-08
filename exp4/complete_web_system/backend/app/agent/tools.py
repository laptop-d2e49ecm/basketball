# -*- coding: utf-8 -*-
"""Agent 工具层：把实验4 后端的服务封装为 LangChain 工具（任务书 5.3.1）。

设计依据 docs/TEAM_PLAN_EXP5.md §3.2 与 exp5/CONTRACT.md §5：
- 同进程直接复用 app/services 实现（与 /api/v1/detect、/api/v1/text/classify 同一份代码），
  避免 async 路由内同步 httpx 自调用的死锁风险；
- 工具失败不抛异常，返回"工具调用失败：..."字符串，让 Agent 继续组织回复（契约第 6 节）；
- 模型进程内单例（首次调用时加载 ONNX/joblib，之后复用）。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langchain.tools import tool

from app.core.config import settings
from app.services.image_detector import ImageDetector
from app.services.text_classifier import TextClassifier

BACKEND_DIR = Path(__file__).resolve().parents[2]
SAMPLES_IMAGES = BACKEND_DIR.parent / "samples" / "images"


@lru_cache(maxsize=1)
def _detector() -> ImageDetector:
    return ImageDetector(settings.image_model_path)


@lru_cache(maxsize=1)
def _classifier() -> TextClassifier:
    return TextClassifier(settings.text_model_path, settings.text_meta_path)


def _resolve_image(image_path: str) -> Path:
    """路径解析：支持绝对路径、仓库相对路径、samples/images 下的简写（如 f000005）。"""
    raw = image_path.strip().strip("\"'")
    if not raw:
        raise FileNotFoundError("图像路径为空")
    p = Path(raw)
    if p.is_absolute():
        if p.is_file():
            return p
    else:
        for base in (BACKEND_DIR.parent, BACKEND_DIR, SAMPLES_IMAGES):
            candidate = base / p
            if candidate.is_file():
                return candidate
    stem = Path(p.name).stem
    if stem:
        hits = sorted(SAMPLES_IMAGES.glob(f"*{stem}*"))
        if hits:
            return hits[0]
    raise FileNotFoundError(
        f"找不到图像 {raw}（可用 samples/images 下的文件名，或 f000005 这类简写）"
    )


@tool
def player_detect(image_path: str) -> str:
    """球员检测工具。给定一张篮球比赛图像的路径，返回图中检测到的球员人数、平均置信度、无效框数量与推理耗时。

    何时调用：用户给出图像路径，或询问"图里有几个人 / 有没有球员 / 检测一下球员"。
    image_path 用用户原话里的路径即可，支持 f000005 这类简写。
    """
    try:
        path = _resolve_image(image_path)
        result = _detector().api_detect(path.read_bytes())
        confs = [box["conf"] for box in result["boxes"]]
        avg_conf = round(sum(confs) / len(confs), 2) if confs else 0.0
        return (
            f"图像 {path.name}：检测到 {result['player_count']} 名球员，"
            f"平均置信度 {avg_conf}，过滤无效框 {result['dropped_boxes']} 个，"
            f"推理耗时 {result['infer_ms']}ms"
        )
    except Exception as exc:  # noqa: BLE001 - 工具失败不中断整轮对话
        return f"工具调用失败：{type(exc).__name__}: {exc}"


@tool
def commentary_classify(text: str) -> str:
    """解说文本分类工具。给定一句中文篮球解说词，返回它描述的动作类别与置信度。

    类别共 11 种：其他、助攻传球、投篮、抢断、暂停换人、比分局势、犯规违例、盖帽、篮板、罚球、阵容战术。
    何时调用：用户给出一句解说/评述文字，并询问"这是什么动作 / 什么类别"。
    """
    try:
        result = _classifier().predict(text)
        if not result["is_basketball_text"]:
            return f"判断：非篮球赛事文本（置信度 {result['confidence']}）"
        top3 = "、".join(f"{t['label']}({t['prob']})" for t in result["top3"])
        return (
            f"分类结果：{result['label']}（置信度 {result['confidence']}）；"
            f"Top3：{top3}；耗时 {result['infer_ms']}ms"
        )
    except Exception as exc:  # noqa: BLE001
        return f"工具调用失败：{type(exc).__name__}: {exc}"


TOOLS = [player_detect, commentary_classify]
