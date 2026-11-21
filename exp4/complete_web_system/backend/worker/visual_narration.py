"""Generate short, timestamped commentary from the actual video pictures."""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import cv2

from worker.commentary.evidence import unsupported
from worker.commentary.llm import content_text
from worker.commentary.vision import FrameGrabber

CUE_MS = 6000
CUES_PER_REQUEST = 1
logger = logging.getLogger("basketball-visual-narration")
PROMPT = (
    "你是篮球直播解说员。输入按时间标记的实际视频帧，请为每个指定时段写一句中文解说。"
    "每段有两组短间隔连续画面，共四张图，只使用该段画面，不引用其他时段、不预告后续。"
    "画面是第一依据，不要根据通用篮球常识编造动作。看得清持球人才说持球人，"
    "优先讲投篮出手、传球、突破、篮板争抢，再讲防守回应，不要用站位描述掩盖主要动作。"
    "投篮动作和命中结果是两件事：连续画面看清持球抬手、球离手并向篮筐飞行时，应明确说投篮出手。"
    "看不清结果就不报命中；不能因为不知道进没进而把投篮改写成举球或起跳。"
    "球被遮挡就描述可见的站位或防守，不猜传球、变向、投篮或球权变化。"
    "球员移动方向变化不等于球变向，举手不等于出手，没有画面依据不说动作已完成。"
    "不要凭单张帧断言球已传出；相邻帧也看不清球的轨迹时只说能看见的动作。"
    "优先用球衣颜色称呼球员；号码只在该球员球衣清晰可读时提到，"
    "不要猜人名、球队、比分、命中、赛果或战术；不要用记分牌推断某人的身份。"
    "每段约6秒，写36到44个汉字的完整口播，短于6秒时按给出的时长缩短。"
    "先说主要动作，再补充画面明确可见的防守反应或无球站位，让听众知道这一段发生了什么。"
    "有足够依据时写两句相连的短句，不只报动作标签；画面信息少时允许短句，不凑字数。"
    "四帧中可见的动作变化、攻防距离与周围站位尽量说清楚，不要把整个过程压成一句二十字的概括。"
    "不报时间戳、不反复说人数，不用夸张套话。"
    "无法确定的动作用‘像是’留有余地，不要用‘随后、接着’串联其他时间点。"
    "只输出JSON对象，格式为{\"sections\":[{\"start_ms\":0,\"text\":\"绿衣持球推进，白衣紧跟防守。\"}]}。"
    "必须逐一返回指定的start_ms，不得增删、改动时间；示例文字仅表示格式，不能照抄事实。"
)

STYLE_PROMPT = (
    "你是篮球现场解说员，现在只做口播润色，不再识别画面。下面每个时段的事实已经核对，"
    "只能换口语、节奏和句式，不能添加动作、位置、号码、战术、心理、结果或新的先后顺序。"
    "每段按给出的时长写口播，6秒段约36到44字，短段按比例缩短；像场边解说，有呼吸、有轻重。"
    "保留已核对事实中的细节，不要润色成比原稿更短的动作标签；信息不足时仍以事实为先。"
    "原稿已确认的投篮、传球、突破必须保留，不要在润色时退化成举手、起跳、移动。"
    "把主动作和防守回应连成完整的讲述，不用连续的动作标签。用停顿、长短句和重音体现现场感。"
    "不能只把逗号换成句号或删掉‘球员’二字，至少一半段落要真正换成自然口语。"
    "例如原事实‘白衣持球推进，绿衣退防’，可说‘白衣带着往前走，绿衣往回跟。’；"
    "原事实‘绿衣右侧突破，白衣紧跟封堵’，可说‘右侧这一步！白衣跟得紧，路还堵着。’。"
    "‘持球’可说‘球还在手里’，‘紧逼盯防’可说‘贴住了，盯得很紧’，"
    "‘贴身干扰’可说‘贴着身，手上还有干扰’；只选原事实确实支持的表达。"
    "把长句拆成短句，动词领句，少重复‘球员’二字。可以说‘球护住。防守贴上来了。’"
    "‘往里这一步！白衣跟得很紧。’但只有原事实里确有护球、突破和跟防时才这样改。"
    "不要每段都写成‘绿衣球员做什么，白衣球员做什么’。相邻段换个起句，"
    "有时点持球动作，有时点已经给出的防守反应，保持自然衔接，不复述上一段动作。"
    "突破、起跳、贴身对抗清楚时，可以短促提气；普通持球时收住，整场最多三分之一的段落用感叹号。"
    "不要喊‘好球、漂亮、精彩’凑气氛；不用‘节奏明显加快、拭目以待’等空话。"
    "特别注意：持球推进不等于反击，跳起不等于出手，突破不等于强起，防守不等于抢断。"
    "保留原事实中的球队颜色、动作主体与动作方向，不要对调攻防。"
    "每个事实块对应一段，原样保留start_ms，输出JSON对象"
    "{\"sections\":[{\"start_ms\":0,\"text\":\"可直接朗读的口播\"}]}。"
)

# A language-only rewrite must not turn a cautious observation into a new play.
_ACTION_GROUPS = (
    ("出手", "投篮", "补篮", "上篮", "扣篮", "强起", "起手"),
    ("篮板", "收下"), ("传球", "传出", "分球", "拨到", "送出"),
    ("快攻", "反击"), ("突破", "往里", "突入", "突进", "冲进"),
    ("起跳", "跃起", "跳起"), ("变向", "换手"), ("倒地", "摔倒"),
    ("掏", "断球", "抢断"), ("封盖", "盖帽"),
    ("压低重心", "重心压"), ("横移", "横着跟"), ("侧身", "侧着身"),
)
_EXACT_DETAILS = ("白衣", "绿衣", "红衣", "蓝衣", "黑衣", "黄衣", "右侧", "左侧", "篮下", "弧顶", "外线")
_KEY_ACTIONS = (("投篮", "出手", "上篮", "补篮", "扣篮"), ("传球", "传出", "分球"), ("突破", "突向", "突入", "往里", "突进", "冲进"))


def _faithful_rewrite(text: str, facts: str) -> bool:
    if any(any(word in facts for word in group) and not any(word in text for word in group)
           for group in _KEY_ACTIONS):
        return False
    if len(text) > 60 or unsupported(text, [{"scene": facts}], None):
        return False
    if any(detail in text and detail not in facts for detail in _EXACT_DETAILS):
        return False
    return not any(any(word in text for word in group) and not any(word in facts for word in group)
                   for group in _ACTION_GROUPS)


def polish_sections(model: Any, sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite diction only; retain original observations when a rewrite adds facts."""
    content = [{"type": "text", "text": STYLE_PROMPT}]
    content.extend({"type": "text", "text": f"指定时段start_ms={row['start_ms']}，时长{(row.get('end_ms', row['start_ms'] + CUE_MS) - row['start_ms']) / 1000:g}秒，已核对事实：{row['text']}"}
                   for row in sections)
    try:
        stylist = model.bind(temperature=.45) if hasattr(model, "bind") else model
        response = stylist.invoke([("user", content)])
        rewritten = parse_sections(content_text(response.content), [row["start_ms"] for row in sections])
    except Exception:
        logger.warning("口播润色失败，保留已核对的画面解说")
        return sections
    return [{**original, "text": revised["text"] if _faithful_rewrite(revised["text"], original["text"])
             else original["text"]} for original, revised in zip(sections, rewritten)]


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
        if not text or len(text) > 70 or unsupported(text, [{"scene": text}], None):
            raise ValueError("画面解说含未支持断言或长度不合适")
        parsed.append({"start_ms": start, "text": text})
    return parsed


def cue_frame_times(start: int, end: int) -> tuple[int, int, int, int]:
    """Two motion pairs using the existing four-image request budget."""
    span = end - start
    gap = min(500, max(1, span // 6))
    first, second = start + span // 3, start + 2 * span // 3
    return first, min(end - 1, first + gap), second, min(end - 1, second + gap)


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
                index = starts.index(start)
                end = starts[index + 1] if index + 1 < len(starts) else duration_ms
                span = end - start
                content.append({"type": "text", "text": f"指定时段start_ms={start}，时长{span / 1000:g}秒；下面四帧只属于此时段。"})
                for timestamp in cue_frame_times(start, end):
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
        try:
            return parse_sections(content_text(response.content), expected)
        except (ValueError, TypeError):
            # Repair only the affected picture batch, instead of discarding all
            # parallel visual results and regenerating the match event by event.
            repair = content + [{"type": "text", "text": "上一稿未通过事实或格式检查。请重写本时段：只说可见动作，禁止命中、得分、赛果断言；保留指定时间，输出完整JSON。"}]
            response = model.invoke([("user", repair)])
            return parse_sections(content_text(response.content), expected)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="visual-narration") as pool:
        sections = [cue for batch in pool.map(describe, batches) for cue in batch]
    for index, section in enumerate(sections):
        end = starts[index + 1] if index + 1 < len(starts) else duration_ms
        section["end_ms"] = end
        section["event_count"] = sum(section["start_ms"] <= int(e.get("t_ms", 0)) < end for e in events)
    sections = polish_sections(model, sections)
    return {
        "task_id": task_id, "status": "ready", "source": "vision",
        "alignment": "video_frames_6s", "style": "live-v4", "created_at": datetime.now(UTC).isoformat(),
        "event_count": len(events), "sections": sections, "tool_calls": [],
        "text": "\n\n".join(section["text"] for section in sections), "error": None,
    }
