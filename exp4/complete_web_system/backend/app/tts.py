from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger("basketball-tts")

# 神经网络语音（edge-tts，免费无 key）。音色/语速可用 .env 覆盖。
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_RATE = "+10%"
_SYNTH_LOCK = threading.Lock()


def narration_text(narration_path: Path) -> str:
    """从解说稿提取待朗读文本：优先 sections 逐段拼接。"""
    result = json.loads(narration_path.read_text(encoding="utf-8"))
    sections = [
        str(section.get("text", "")).strip()
        for section in result.get("sections", [])
        if str(section.get("text", "")).strip()
    ]
    return "\n".join(sections) or str(result.get("text", "")).strip()


def synthesize_narration(narration_path: Path) -> Path:
    """把整场解说稿合成为 MP3，与解说稿同目录缓存；解说稿更新后自动重合成。"""
    audio_path = narration_path.with_name("narration.mp3")
    with _SYNTH_LOCK:
        if audio_path.exists() and audio_path.stat().st_mtime >= narration_path.stat().st_mtime:
            return audio_path
        text = narration_text(narration_path)
        if not text:
            raise ValueError("解说稿为空，无法合成语音")
        try:
            import edge_tts
        except ImportError as exc:  # 依赖未装不应让接口 500，交给上层转 503
            raise RuntimeError("语音合成依赖未安装：请执行 pip install edge-tts 后重试") from exc
        voice = os.getenv("BASKETBALL_TTS_VOICE", DEFAULT_VOICE)
        rate = os.getenv("BASKETBALL_TTS_RATE", DEFAULT_RATE)

        def _run() -> bytes:
            async def _collect() -> bytes:
                communicate = edge_tts.Communicate(text, voice, rate=rate)
                data = bytearray()
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        data.extend(chunk["data"])
                return bytes(data)

            return asyncio.run(_collect())

        data = _run()
        if not data:
            raise RuntimeError("语音合成返回空音频，请检查网络后重试")
        temporary = audio_path.with_suffix(".mp3.tmp")
        temporary.write_bytes(data)
        temporary.replace(audio_path)
        logger.info("整场解说语音已合成：%s (%d bytes)", audio_path.name, len(data))
        return audio_path
