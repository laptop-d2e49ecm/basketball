from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from pathlib import Path

logger = logging.getLogger("basketball-tts")

# 神经网络语音（edge-tts，免费无 key）。音色/语速可用 .env 覆盖。
# 云健是微软官方的体育解说男声；零成本档用「按句动态韵律」制造激情：
# 含「！」的高潮句加速抬调，平铺句用基础语速，避免整场一个调门的"平静朗读"。
DEFAULT_VOICE = "zh-CN-YunjianNeural"
DEFAULT_RATE = "+10%"
DEFAULT_CLIMAX_RATE = "+35%"
DEFAULT_CLIMAX_PITCH = "+25Hz"
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*")
_SYNTH_LOCK = threading.Lock()


def narration_text(narration_path: Path) -> str:
    """从解说稿提取待合成文本：优先 sections 逐段拼接。"""
    result = json.loads(narration_path.read_text(encoding="utf-8"))
    sections = [
        str(section.get("text", "")).strip()
        for section in result.get("sections", [])
        if str(section.get("text", "")).strip()
    ]
    return "\n".join(sections) or str(result.get("text", "")).strip()


def _prosody_chunks(text: str) -> list[tuple[str, bool]]:
    """按句切分并标注是否高潮句；相邻同风格句子合并成块，控制合成请求数。

    climax 判定：句内含「！」或“!”——解说稿的爆发点都落在感叹号上。
    """
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    chunks: list[tuple[str, bool]] = []
    for sentence in sentences:
        climax = "！" in sentence or "!" in sentence
        if chunks and chunks[-1][1] == climax:
            chunks[-1] = (chunks[-1][0] + sentence, climax)
        else:
            chunks.append((sentence, climax))
    return chunks


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
        climax_rate = os.getenv("BASKETBALL_TTS_CLIMAX_RATE", DEFAULT_CLIMAX_RATE)
        climax_pitch = os.getenv("BASKETBALL_TTS_CLIMAX_PITCH", DEFAULT_CLIMAX_PITCH)
        chunks = _prosody_chunks(text)

        def _run() -> bytes:
            async def _collect() -> bytes:
                data = bytearray()
                for chunk, climax in chunks:
                    communicate = edge_tts.Communicate(
                        chunk,
                        voice,
                        rate=climax_rate if climax else rate,
                        pitch=climax_pitch if climax else "+0Hz",
                    )
                    async for piece in communicate.stream():
                        if piece["type"] == "audio":
                            data.extend(piece["data"])
                return bytes(data)

            return asyncio.run(_collect())

        data = _run()
        if not data:
            raise RuntimeError("语音合成返回空音频，请检查网络后重试")
        temporary = audio_path.with_suffix(".mp3.tmp")
        temporary.write_bytes(data)
        temporary.replace(audio_path)
        logger.info(
            "整场解说语音已合成：%s (%d bytes, %d 块/高潮 %d)",
            audio_path.name, len(data), len(chunks), sum(1 for _, c in chunks if c),
        )
        return audio_path
