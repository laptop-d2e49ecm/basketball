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
    """极简 .env 解析（与 app.core.config 的 dotenv 加载互不干扰）。

    同名环境变量优先于 .env 文件——便于临时改超时/后端而不用动文件
    （例如 `$env:EXP5_LLM_TIMEOUT=2` 后再起服务，用于故障注入测试）。
    """
    import os

    cfg: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip().strip("'\"")
    for key in list(cfg.keys()) + [k for k in os.environ if k.startswith("EXP5_")]:
        if key in os.environ:
            cfg[key] = os.environ[key]
    return cfg


def make_chat_model():
    """按 .env 构造 ChatOpenAI；key 未配置时抛 RuntimeError（由 API 层转 500）。

    默认直连不走系统代理（EXP5_LLM_TRUST_ENV=1 可改回走代理）——
    本机若开着 VPN/Clash 类代理，httpx 默认 trust_env 会把 LLM 请求也劫持进代理，
    造成偶发超时/慢响应；国内中转端点直连更稳。
    """
    import httpx
    from langchain_openai import ChatOpenAI

    cfg = load_env()
    api_key = cfg.get("EXP5_LLM_API_KEY", "")
    if not api_key or "粘贴" in api_key or "填" in api_key:
        raise RuntimeError(f"大模型 key 未配置，请编辑 {ENV_PATH}")
    trust_env = cfg.get("EXP5_LLM_TRUST_ENV", "0") == "1"
    timeout = float(cfg.get("EXP5_LLM_TIMEOUT", "60"))
    return ChatOpenAI(
        model=cfg.get("EXP5_LLM_MODEL", "deepseek-v4.1-flash-1017"),
        base_url=cfg.get("EXP5_LLM_BASE_URL", ""),
        api_key=api_key,
        temperature=0,
        timeout=timeout,
        http_client=httpx.Client(trust_env=trust_env, timeout=timeout),
    )
