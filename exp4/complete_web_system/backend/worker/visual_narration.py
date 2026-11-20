"""Generate short, timestamped commentary from the actual video pictures."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import cv2

from worker.commentary.evidence import unsupported
from worker.commentary.llm import content_text
from worker.commentary.vision import FrameGrabber

CUE_MS = 3000
CUES_PER_REQUEST = 2
PROMPT = (
    "你是篮球直播解说员。输入按时间标记的实际视频帧，请为每个指定时段写一句中文解说。"
    "每段只使用该段起始时刻和紧接的0.5秒画面，不要引用其他时段的动作，不要预告后续。"
    "画面是第一依据，不要根据通用篮球常识编造动作。看得清持球人才说持球人，"
    "球被遮挡就描述可见的站位或防守，不猜传球、变向、投篮或球权变化。"
    "球员移动方向变化不等于球变向，举手不等于出手，没有画面依据不说动作已完成。"
    "不要凭单张帧断言球已传出；相邻帧也看不清球的轨迹时只说能看见的动作。"
    "优先用球衣颜色称呼球员；号码只在该球员球衣清晰可读时提到，"
    "不要猜人名、球队、比分、命中、赛果或战术；不要用记分牌推断某人的身份。"
    "每句约12到18个汉字，语气自然完整，不报时间戳、不反复说人数，不用夸张套话。"
    "无法确定的动作用‘像是’留有余地，不要用‘随后、接着’串联其他时间点。"
    "只输出JSON对象，格式为{\"sections\":[{\"start_ms\":0,\"text\":\"绿衣持球推进，白衣紧跟防守。\"}]}。"
    "必须逐一返回指定的start_ms，不得增删、改动时间；示例文字仅表示格式，不能照抄事实。"
)


def parse_sections(raw: str, starts: list[int]) -> list[dict[str, Any]]:
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    payload = json.loads(raw)
    rows = payload.get("sections") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) != len(starts):
        raise ValueError("画面解说缺少时间段")
    parsed = []
    for row, start in zip(rows, starts):
        if not isinstance(row, dict) or row.get("start_ms") != start:
            raise ValueError("画面解说时间不匹配")
        text = str(row.get("text") or "").strip()
        if not text or len(text) > 45 or unsupported(text, [{"scene": text}], None):
            raise ValueError("画面解说含未支持断言或长度不合适")
        parsed.append({"start_ms": start, "text": text})
    return parsed


def generate_visual_narration(
    task_id: str, video_path: Path, events: list[dict[str, Any]], *,
    model_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    from app.agent.providers import make_vision_model

    cap = cv2.VideoCapture(str(video_path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    finally:
        cap.release()
    if fps <= 0 or frames <= 0:
        raise ValueError("无法读取视频时长")
    duration_ms = round(frames / fps * 1000)
    # Keep a tiny final remainder with the previous cue.
    starts = [start for start in range(0, duration_ms, CUE_MS)
              if start == 0 or duration_ms - start >= 1000]
    model = (model_factory or make_vision_model)()
    grabber = FrameGrabber(str(video_path))
    batches = []
    try:
        for offset in range(0, len(starts), CUES_PER_REQUEST):
            batch = starts[offset:offset + CUES_PER_REQUEST]
            content: list[dict[str, Any]] = [{"type": "text", "text": PROMPT}]
            for start in batch:
                content.append({"type": "text", "text": f"指定时段start_ms={start}，约3秒；下面两帧只属于此时段。"})
                for timestamp in (start, min(start + 500, duration_ms - 40)):
                    jpeg = grabber.jpeg_b64(timestamp)
                    if not jpeg:
                        raise ValueError("画面解说抓帧失败")
                    content.extend([
                        {"type": "text", "text": f"视频实际时间{timestamp}毫秒"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg}"}},
                    ])
            batches.append((batch, content))
    finally:
        grabber.close()

    def describe(batch):
        expected, content = batch
        response = model.invoke([("user", content)])
        return parse_sections(content_text(response.content), expected)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="visual-narration") as pool:
        sections = [cue for batch in pool.map(describe, batches) for cue in batch]
    for index, section in enumerate(sections):
        end = starts[index + 1] if index + 1 < len(starts) else duration_ms
        section["end_ms"] = end
        section["event_count"] = sum(section["start_ms"] <= int(e.get("t_ms", 0)) < end for e in events)
    return {
        "task_id": task_id, "status": "ready", "source": "vision",
        "alignment": "video_frames_3s", "created_at": datetime.now(UTC).isoformat(),
        "event_count": len(events), "sections": sections, "tool_calls": [],
        "text": "\n\n".join(section["text"] for section in sections), "error": None,
    }
