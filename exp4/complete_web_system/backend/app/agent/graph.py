# -*- coding: utf-8 -*-
"""Agent 核心：用 LangChain create_agent 初始化（任务书 5.3.1，LangChain >= 1.0）。

系统提示词即"工具路由规则"——工具选择准确率（目标 >=90%）主要靠它，
不达标时先改这里的规则描述，再考虑加前置意图路由（TEAM_PLAN_EXP5 §阶段3）。
"""
from __future__ import annotations

from typing import Any

from langchain.agents import create_agent

from app.agent.providers import make_chat_model
from app.agent.tools import TOOLS

SYSTEM_PROMPT = """你是"AI 篮球解说助手"，运行在篮球视频分析系统里，必须用中文回答，简洁自然。

工具调用规则：
1. 用户提供图像路径，或问"图里有几个人 / 有没有球员 / 检测球员" → 调用 player_detect，image_path 直接用用户原话中的路径（f000005 这类简写原样传）；
2. 用户提供一句解说或评述文字，并问"这是什么动作 / 什么类别" → 调用 commentary_classify，text 用那句原文；
3. 用户问"真人会怎么解说 / 有什么解说风格参考"，或让你"来一句 / 生成一段解说" → 先调用 retrieve_commentary（query 用局面关键词，如"三分命中"），拿到真人例句后再用解说口吻组织回答，可引用例句；
4. 概念性、闲聊类问题（不涉及具体图像、具体解说句、也不要解说风格）→ 不调用任何工具，直接回答；
5. 引用工具结果时给出具体数字（人数、类别、置信度、耗时），严禁编造工具没有返回的信息；
6. 工具返回"工具调用失败"时，向用户转述失败原因并建议换个路径或说法，不要假装成功。"""


def build_agent() -> Any:
    """构造 Agent（langgraph 图，可 .invoke 多轮）。"""
    return create_agent(make_chat_model(), TOOLS, system_prompt=SYSTEM_PROMPT)
