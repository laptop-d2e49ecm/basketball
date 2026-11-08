# -*- coding: utf-8 -*-
"""实验5 大模型连通性自检脚本。

用法（仓库根目录运行）:
    pip install openai          # 只需装一次
    python exp5/test_api.py

它做三件事:
  1. 读取 exp4/complete_web_system/backend/.env 里的配置；
  2. 列出你的 key 可用的模型（把 deepseek 的准确 id 填回 .env 的 EXP5_LLM_MODEL）；
  3. 用当前配置的模型问一句话，打印回复。
"""
from pathlib import Path
import sys

ENV_PATH = Path(__file__).resolve().parent.parent / "exp4" / "complete_web_system" / "backend" / ".env"


def load_env(path: Path) -> dict:
    cfg = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip().strip("'\"")
    return cfg


def main() -> int:
    if not ENV_PATH.exists():
        print(f"[x] 找不到配置文件: {ENV_PATH}")
        return 1
    cfg = load_env(ENV_PATH)
    base_url = cfg.get("EXP5_LLM_BASE_URL", "")
    api_key = cfg.get("EXP5_LLM_API_KEY", "")
    model = cfg.get("EXP5_LLM_MODEL", "")

    if not api_key or "粘贴" in api_key or "填" in api_key:
        print(f"[x] 请先在 {ENV_PATH} 里把 EXP5_LLM_API_KEY 换成你的真实 key")
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("[x] 缺少依赖，先运行: pip install openai")
        return 1

    client = OpenAI(base_url=base_url, api_key=api_key)

    # 第一步：列出可用模型（从中确认 deepseek 的准确 id）
    try:
        ids = [m.id for m in client.models.list()]
        print(f"[1/2] key 有效。可用模型 {len(ids)} 个：")
        for i in ids:
            mark = "  <-- 当前配置" if i == model else ""
            print(f"      {i}{mark}")
        if model not in ids:
            deepseek_like = [i for i in ids if "deepseek" in i.lower()]
            if deepseek_like:
                print(f"[i] 你 .env 里的模型名不在列表中，deepseek 相关的有: {deepseek_like}，选一个填回 EXP5_LLM_MODEL")
    except Exception as e:
        print(f"[!] 拉取模型列表失败（不影响使用，可能是中转站不支持此接口）: {e}")

    # 第二步：真实问答一次
    print(f"\n[2/2] 用 {model} 问一句话测试 ...")
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "用一句话介绍篮球解说员的作用"}],
        )
        print(f"[OK] 配置全部正确！模型回复：\n      {resp.choices[0].message.content}")
        print("\n下一步：把 base_url / api_key / model 三行的确认结果告诉组长，就可以接 Agent 后端了。")
        return 0
    except Exception as e:
        print(f"[x] 问答失败: {e}")
        print("    排查: ①key 是否复制完整 ②模型名是否在上方列表里 ③网络/代理")
        return 1


if __name__ == "__main__":
    sys.exit(main())
