"""Join the existing voice clips into a single video-aligned audio track."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from pathlib import Path

from app.tts import synthesize_narration

_LOCK = threading.Lock()
_SAMPLE_RATE = 24000


def _run(arguments: list[str], timeout: int = 60, *, data: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(arguments, input=data, capture_output=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("连续解说音轨准备失败，请重试") from exc
    if result.returncode:
        raise RuntimeError("连续解说音轨无法读取分段语音，请重试")
    return result.stdout


def _tempo(rate: float) -> str:
    filters = []
    while rate > 2:
        filters.append("atempo=2")
        rate /= 2
    filters.append(f"atempo={rate:.9f}")
    return ",".join(filters)


def synthesize_timeline(narration_path: Path) -> Path:
    import imageio_ffmpeg

    with _LOCK:
        narration = json.loads(narration_path.read_text(encoding="utf-8"))
        sections = narration.get("sections") or []
        if not sections:
            raise ValueError("解说时间段尚未准备好")
        starts = [int(row.get("start_ms", 0)) for row in sections]
        ends = starts[1:] + [int(sections[-1].get("end_ms") or 0)]
        if starts[0] < 0 or any(end <= start for start, end in zip(starts, ends)):
            raise ValueError("解说时间范围不正确")
        files = [synthesize_narration(narration_path, i) for i in range(len(sections))]
        digest = hashlib.sha256(b"timeline-pcm-v2")
        digest.update(json.dumps([starts, ends]).encode())
        for file in files:
            digest.update(file.read_bytes())
        profile = digest.hexdigest()
        target = narration_path.with_name("narration-timeline.mp3")
        profile_path = target.with_suffix(".voice.json")
        if target.is_file() and profile_path.is_file() and profile_path.read_text(encoding="utf-8") == profile:
            return target

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        # Decode real samples: MP3 headers, padding and concatenated prosody
        # chunks can give browser duration estimates that cut off spoken words.
        # Stream one cue at a time: long matches must not exceed Windows'
        # command-line limit or retain the whole decoded match in memory.
        pcm_path = target.with_suffix(".pcm.tmp")
        temporary = target.with_suffix(".mp3.tmp")
        try:
            with pcm_path.open("wb") as output:
                output.write(b"\0" * round(starts[0] / 1000 * _SAMPLE_RATE * 2))
                for file, start, end in zip(files, starts, ends):
                    pcm = _run([exe, "-v", "error", "-i", str(file), "-ac", "1", "-ar", str(_SAMPLE_RATE),
                                "-f", "s16le", "pipe:1"])
                    duration = len(pcm) / (_SAMPLE_RATE * 2)
                    if duration <= 0:
                        raise ValueError("分段语音为空")
                    span = (end - start) / 1000
                    # Leave a few samples of breathing room instead of cutting
                    # a final consonant when atempo rounds its output length.
                    rate = max(.8, duration / max(.05, span - .025))
                    aligned = _run([exe, "-v", "error", "-f", "s16le", "-ac", "1", "-ar", str(_SAMPLE_RATE),
                        "-i", "pipe:0", "-af", f"{_tempo(rate)},apad,atrim=duration={span:.6f}",
                        "-f", "s16le", "pipe:1"], data=pcm)
                    size = round(span * _SAMPLE_RATE) * 2
                    output.write(aligned[:size].ljust(size, b"\0"))
            _run([exe, "-y", "-v", "error", "-f", "s16le", "-ac", "1", "-ar", str(_SAMPLE_RATE),
                  "-i", str(pcm_path), "-codec:a", "libmp3lame", "-b:a", "96k", "-f", "mp3", str(temporary)], timeout=120)
            temporary.replace(target)
        finally:
            pcm_path.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
        profile_path.write_text(profile, encoding="utf-8")
        return target
