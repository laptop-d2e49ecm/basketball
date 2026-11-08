# -*- coding: utf-8 -*-
"""大模型接入层：从后端 .env 读配置，构造 LangChain ChatOpenAI 客户端（OpenAI 兼容端点通用）。

配置文件（唯一一处）：backend/.env（模板见仓库 exp5/.env.example，勿提交 git）
  EXP5_LLM_PROVIDER / EXP5_LLM_BASE_URL / EXP5_LLM_API_KEY / EXP5_LLM_MODEL
"""
from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BACKEND_DIR / ".env"


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    """极简 .env 解析（与 app.core.config 的 dotenv 加载互不干扰）。"""
    cfg: dict[str, str] = {}
    if not path.is_file():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cfg[key.strip()] = value.strip().strip("'\"")
    return cfg


def make_chat_model():
    """按 .env 构造 ChatOpenAI；key 未配置时抛 RuntimeError（由 API 层转 500）。"""
    from langchain_openai import ChatOpenAI

    cfg = load_env()
    api_key = cfg.get("EXP5_LLM_API_KEY", "")
    if not api_key or "粘贴" in api_key or "填" in api_key:
        raise RuntimeError(f"大模型 key 未配置，请编辑 {ENV_PATH}")
    return ChatOpenAI(
        model=cfg.get("EXP5_LLM_MODEL", "deepseek-v4.1-flash-1017"),
        base_url=cfg.get("EXP5_LLM_BASE_URL", ""),
        api_key=api_key,
        temperature=0,
        timeout=60,
    )
