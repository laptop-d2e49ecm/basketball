from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
from urllib.request import getproxies
from urllib.parse import urlsplit
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
_SYNTH_LOCKS = [threading.Lock() for _ in range(64)]
_SYNTH_CAPACITY = threading.BoundedSemaphore(3)
_REQUEST_TIMEOUT = 90
_RETRY_DELAY = 0.3


def _trim_segment_silence(data: bytes) -> bytes:
    """Remove only the leading/trailing silence; preserve pauses inside speech."""
    if len(data) < 1024:
        return data
    try:
        import imageio_ffmpeg

        trim = "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB:start_silence=0.04"
        output = subprocess.run([
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-f", "mp3", "-i", "pipe:0", "-af", f"{trim},areverse,{trim},areverse",
            "-codec:a", "libmp3lame", "-b:a", "48k", "-f", "mp3", "pipe:1",
        ], input=data, capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if output.returncode == 0 and output.stdout:
            return output.stdout
    except (ImportError, OSError, subprocess.TimeoutExpired):
        logger.warning("分段音频静音裁剪失败，保留原始语音")
    return data


def _speech_proxy() -> str | None:
    """WebSocket speech requests need the Windows HTTP proxy passed explicitly."""
    configured = os.getenv("BASKETBALL_TTS_PROXY", "auto").strip()
    if configured.lower() in {"direct", "none", "off"}:
        return None
    if not configured or configured.lower() == "auto":
        proxies = getproxies()
        configured = proxies.get("wss") or proxies.get("https") or proxies.get("http") or proxies.get("all") or ""
    if not configured:
        return None
    if "://" not in configured:
        configured = "http://" + configured
    if urlsplit(configured).scheme.lower() not in {"http", "https"}:
        raise RuntimeError("语音代理需为 HTTP 或 HTTPS 地址")
    return configured


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

    与 .new 一致，仅感叹句使用加速、抬调参数。
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


def synthesize_narration(narration_path: Path, section: int | None = None) -> Path:
    """把整场解说稿合成为 MP3，与解说稿同目录缓存；解说稿更新后自动重合成。"""
    if section is None:
        audio_path = narration_path.with_name("narration.mp3")
        text = narration_text(narration_path)
    else:
        sections = json.loads(narration_path.read_text(encoding="utf-8")).get("sections") or []
        if not 0 <= section < len(sections):
            raise ValueError("解说段落不存在")
        text = str(sections[section].get("text") or "").strip()
        audio_path = narration_path.with_name(f"narration-section-{section}.mp3")
    lock_index = int(hashlib.sha256(str(audio_path.resolve()).encode()).hexdigest(), 16) % len(_SYNTH_LOCKS)
    with _SYNTH_LOCKS[lock_index], _SYNTH_CAPACITY:
        voice = os.getenv("BASKETBALL_TTS_VOICE", DEFAULT_VOICE)
        rate = os.getenv("BASKETBALL_TTS_RATE", DEFAULT_RATE)
        climax_rate = os.getenv("BASKETBALL_TTS_CLIMAX_RATE", DEFAULT_CLIMAX_RATE)
        climax_pitch = os.getenv("BASKETBALL_TTS_CLIMAX_PITCH", DEFAULT_CLIMAX_PITCH)
        profile_path = audio_path.with_suffix(".voice.json")
        profile = json.dumps(["edge-segment-trim-v2" if section is not None else "edge-new-v1", voice, rate, climax_rate, climax_pitch, hashlib.sha256(text.encode("utf-8")).hexdigest()])
        if (audio_path.is_file() and profile_path.is_file()
                and profile_path.read_text(encoding="utf-8") == profile
                and audio_path.stat().st_mtime_ns >= narration_path.stat().st_mtime_ns):
            return audio_path
        if not text:
            raise ValueError("解说稿为空，无法合成语音")
        try:
            import edge_tts
        except ImportError as exc:  # 依赖未装不应让接口 500，交给上层转 503
            raise RuntimeError("语音合成依赖未安装：请执行 pip install edge-tts 后重试") from exc
        chunks = _prosody_chunks(text)
        proxy = _speech_proxy()

        def _run() -> bytes:
            async def _collect() -> bytes:
                data = bytearray()
                for chunk, climax in chunks:
                    communicate = edge_tts.Communicate(
                        chunk,
                        voice,
                        rate=climax_rate if climax else rate,
                        pitch=climax_pitch if climax else "+0Hz",
                        proxy=proxy,
                        connect_timeout=8,
                        receive_timeout=20,
                    )
                    start = len(data)
                    async for piece in communicate.stream():
                        if piece["type"] == "audio":
                            data.extend(piece["data"])
                    if len(data) == start:
                        raise RuntimeError("部分解说未返回语音，请稍后重试")
                return bytes(data)

            async def _bounded() -> bytes:
                return await asyncio.wait_for(_collect(), timeout=_REQUEST_TIMEOUT)
            return asyncio.run(_bounded())

        for attempt in range(2):
            try:
                data = _run()
                break
            except Exception as exc:
                logger.warning("在线语音请求失败（%s），%s", type(exc).__name__, "重试一次" if attempt == 0 else "停止重试")
                if attempt == 1:
                    raise RuntimeError("无法连接在线语音服务，请检查系统代理或网络后重试") from exc
                time.sleep(_RETRY_DELAY)
        if not data:
            raise RuntimeError("语音合成返回空音频，请检查网络后重试")
        if section is not None:
            data = _trim_segment_silence(data)
        temporary = audio_path.with_suffix(".mp3.tmp")
        temporary.write_bytes(data)
        temporary.replace(audio_path)
        profile_path.write_text(profile, encoding="utf-8")
        logger.info(
            "整场解说语音已合成：%s (%d bytes, %d 块/高潮 %d)",
            audio_path.name, len(data), len(chunks), sum(1 for _, c in chunks if c),
        )
        return audio_path
