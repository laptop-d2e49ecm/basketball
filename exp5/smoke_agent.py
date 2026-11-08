# -*- coding: utf-8 -*-
"""Agent 冒烟入口（仓库根目录运行，方便记忆）。

    .venv\\Scripts\\python.exe exp5/smoke_agent.py

Agent 代码的正式位置在后端内：exp4/complete_web_system/backend/app/agent/
（系统自包含，队友拿 complete_web_system.zip 也能跑）。
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "exp4" / "complete_web_system" / "backend"
sys.path.insert(0, str(BACKEND))

from app.agent.smoke import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
