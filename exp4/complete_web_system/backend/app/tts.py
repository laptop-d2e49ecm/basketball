from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import threading
import time
from urllib.request import getproxies
from urllib.parse import urlsplit
from pathlib import Path

logger = logging.getLogger("basketball-tts")

# 神经网络语音（edge-tts，免费无 key）。音色/语速可用 .env 覆盖。
# 全场使用同一组声线参数，标点不再触发额外抬调或加速。
DEFAULT_VOICE = "zh-CN-YunjianNeural"
DEFAULT_RATE = "+10%"
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
        profile_path = audio_path.with_suffix(".voice.json")
        version = "edge-uniform-segment-v4" if section is not None else "edge-uniform-full-v4"
        profile = json.dumps([version, voice, rate, "+0Hz", hashlib.sha256(text.encode("utf-8")).hexdigest()])
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
        proxy = _speech_proxy()

        def _run() -> bytes:
            async def _collect() -> bytes:
                data = bytearray()
                communicate = edge_tts.Communicate(
                    text, voice, rate=rate, pitch="+0Hz", proxy=proxy,
                    connect_timeout=8, receive_timeout=20,
                )
                async for piece in communicate.stream():
                    if piece["type"] == "audio":
                        data.extend(piece["data"])
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
            "统一声线语音已合成：%s (%d bytes)", audio_path.name, len(data),
        )
        return audio_path
