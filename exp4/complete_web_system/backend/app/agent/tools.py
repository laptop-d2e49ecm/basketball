# -*- coding: utf-8 -*-
"""Agent 工具层：把实验4 后端的服务封装为 LangChain 工具（任务书 5.3.1）。

设计依据 docs/TEAM_PLAN_EXP5.md §3.2 与 exp5/CONTRACT.md §5：
- 同进程直接复用 app/services 实现（与 /api/v1/detect、/api/v1/text/classify 同一份代码），
  避免 async 路由内同步 httpx 自调用的死锁风险；
- 工具失败不抛异常，返回"工具调用失败：..."字符串，让 Agent 继续组织回复（契约第 6 节）；
- 模型进程内单例（首次调用时加载 ONNX/joblib，之后复用）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from langchain.tools import tool
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from app.core.config import settings
from app.services.image_detector import ImageDetector
from app.services.match_workflow import run_match
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


# ---- RAG：真人解说语料检索（sklearn 字级 TF-IDF，零新增依赖） ----
# 语料查找顺序：.env 的 EXP5_CORPUS_PATH → 仓库 data 目录 → backend/ml/（独立部署时的放置位）
_CORPUS_CANDIDATES = [
    BACKEND_DIR / "ml" / "livetext_train.jsonl",
    BACKEND_DIR.parents[2] / "data" / "processed" / "texts" / "livetext" / "split_train.jsonl",
]


def _find_corpus() -> Path | None:
    from app.agent.providers import load_env

    env_value = load_env().get("EXP5_CORPUS_PATH", "")
    candidates = ([Path(env_value)] if env_value else []) + _CORPUS_CANDIDATES
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def _commentary_index() -> dict | None:
    """首次调用时建索引（约 3 万条、秒级）；语料缺失返回 None（工具报错但不影响其他功能）。"""
    corpus_path = _find_corpus()
    if corpus_path is None:
        return None
    lines: list[dict] = []
    with corpus_path.open(encoding="utf-8") as fh:
        for raw in fh:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            text = str(item.get("text", "")).strip()
            if 4 <= len(text) <= 120:  # 过滤空句/超长流水账，保持例句可用性
                lines.append(text)
    if not lines:
        return None
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), max_features=80000)
    matrix = vectorizer.fit_transform(lines)
    return {"lines": lines, "vectorizer": vectorizer, "matrix": matrix, "path": corpus_path}


@tool
def retrieve_commentary(query: str, top_k: int = 3) -> str:
    """真人解说语料检索工具。给定比赛局面描述或关键词，从 3 万条真人篮球解说中返回最相似的几条原句（附相似度）。

    何时调用：用户问"真人会怎么解说 / 解说风格参考"，或让你"来一句/生成一段解说"时——
    先用局面关键词调本工具拿真人例句，再基于例句组织回答，风格更真实。
    query 填局面关键词（如"三分出手命中""快攻上篮"），top_k 默认 3。
    """
    try:
        index = _commentary_index()
        if index is None:
            return "工具调用失败：解说语料库未配置（缺 split_train.jsonl；可在 backend/.env 设 EXP5_CORPUS_PATH 指向语料文件）"
        top_k = max(1, min(int(top_k), 5))
        query_vec = index["vectorizer"].transform([query.strip()])
        sims = linear_kernel(query_vec, index["matrix"]).ravel()
        if float(sims.max()) < 0.05:
            return "没有检索到足够相似的真人解说，建议换个更具体的局面关键词（如'三分命中''快攻上篮'）"
        order = sims.argsort()[::-1][:top_k]
        parts = [f"{rank}. {index['lines'][int(i)]}（相似度 {sims[i]:.2f}）" for rank, i in enumerate(order, 1)]
        return "真人解说参考：\n" + "\n".join(parts)
    except Exception as exc:  # noqa: BLE001
        return f"工具调用失败：{type(exc).__name__}: {exc}"


@tool
def image_text_match(image_path: str, text: str) -> str:
    """图文匹配工具。给定一张图像路径和一句文字，判断两者是否同为篮球比赛内容（图像侧检测球员 + 文本侧判断是否篮球解说），返回匹配结论与两侧证据。

    何时调用：用户同时给出图像和一句话，问"这张图和这句话匹不匹配 / 是否相关"。
    """
    try:
        path = _resolve_image(image_path)
        result = run_match(_detector(), _classifier(), path.read_bytes(), text)
        conclusion = "匹配（两侧均为篮球比赛内容）" if result["match"] else "不匹配"
        evidence = "；".join(result["evidence"])
        return f"结论：{conclusion}。证据：{evidence}。总耗时 {result['total_ms']}ms"
    except Exception as exc:  # noqa: BLE001
        return f"工具调用失败：{type(exc).__name__}: {exc}"


@tool
def query_video_events(task_id: str) -> str:
    """视频事件查询工具。给定一个视频分析任务编号，返回该任务产出的关键事件列表（事件类型、发生时间、人数等）。

    何时调用：用户给出任务编号（32 位十六进制，来自视频分析页提交视频后的结果），问"这个视频里发生了什么 / 有哪些事件"。
    """
    try:
        from app.db import task_repo

        task_id = task_id.strip()
        row = task_repo.get_task(task_id)
        if row is None:
            return f"工具调用失败：任务 {task_id} 不存在（可在视频分析页提交视频获得任务编号）"
        events_path = settings.runs_dir / task_id / "events.jsonl"
        if not events_path.is_file():
            return f"任务 {task_id} 暂无事件文件（可能仍在分析中，或未产生关键事件）"
        events = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if not events:
            return f"任务 {task_id} 未产生关键事件"
        parts = []
        for event in events[:8]:
            t_ms = event.get("t_ms")
            when = f"{t_ms / 1000:.1f}" if isinstance(t_ms, (int, float)) else "?"
            etype = event.get("type", "事件")
            extra = {k: v for k, v in event.items() if k in ("player_count", "message", "text") and v not in (None, "")}
            parts.append(f"[{when}s] {etype} {extra if extra else ''}".strip())
        summary = f"（共 {len(events)} 个事件，仅列前 8 个）" if len(events) > 8 else f"（共 {len(events)} 个事件）"
        return f"任务 {task_id}（视频 {row['video_name']}）的关键事件：\n" + "\n".join(parts) + f"\n{summary}"
    except Exception as exc:  # noqa: BLE001
        return f"工具调用失败：{type(exc).__name__}: {exc}"


TOOLS = [player_detect, commentary_classify, retrieve_commentary, image_text_match, query_video_events]
