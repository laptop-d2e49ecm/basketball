from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterator


def iter_heuristic_events(
    detections_path: Path,
    *,
    interval_ms: int = 10_000,
    change_cooldown_ms: int = 3_000,
    change_threshold: int = 2,
    cluster_radius: float = 0.16,
    cluster_cooldown_ms: int = 8_000,
) -> Iterator[dict[str, Any]]:
    """Create conservative visual events from player detections.

    The detector does not identify basketball actions, so these events describe
    only what is visible in the player detections.
    """
    last_event_ms = -interval_ms
    last_event_count: int | None = None
    last_cluster_ms = -cluster_cooldown_ms
    last_cluster_sample_ms = -1_000
    last_direction_ms = -8_000
    last_direction_sample_ms = -1_000
    previous_centroid: tuple[int, float, float] | None = None
    previous_motion: tuple[float, float] | None = None

    with detections_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            frame = json.loads(line)
            timestamp_ms = int(frame.get("t_ms", 0))
            boxes = frame.get("boxes", [])
            player_count = len(boxes)
            track_ids = sorted(
                {
                    int(box["track_id"])
                    for box in boxes
                    if box.get("track_id") is not None
                }
            )

            first_event = last_event_count is None
            count_changed = (
                last_event_count is not None
                and abs(player_count - last_event_count) >= change_threshold
                and timestamp_ms - last_event_ms >= change_cooldown_ms
            )
            periodic_update = timestamp_ms - last_event_ms >= interval_ms
            if first_event or count_changed or periodic_update:
                if first_event:
                    event_type = "player_count"
                elif count_changed:
                    event_type = "player_count_change"
                else:
                    event_type = "player_count_snapshot"
                yield {
                    "t_ms": timestamp_ms,
                    "type": event_type,
                    "source": "heuristic",
                    "player_count": player_count,
                    "track_ids": track_ids,
                }
                last_event_ms = timestamp_ms
                last_event_count = player_count

            sample_cluster = timestamp_ms - last_cluster_sample_ms >= 1_000
            if sample_cluster:
                last_cluster_sample_ms = timestamp_ms
            if sample_cluster and timestamp_ms - last_cluster_ms >= cluster_cooldown_ms and len(boxes) >= 3:
                best_cluster: list[dict[str, Any]] = []
                for candidate in boxes:
                    cx = float(candidate.get("cx", 0))
                    cy = float(candidate.get("cy", 0))
                    nearby = [
                        box
                        for box in boxes
                        if math.hypot(float(box.get("cx", 0)) - cx, float(box.get("cy", 0)) - cy)
                        <= cluster_radius
                    ]
                    if len(nearby) > len(best_cluster):
                        best_cluster = nearby
                if len(best_cluster) >= 3:
                    yield {
                        "t_ms": timestamp_ms,
                        "type": "player_cluster",
                        "source": "heuristic",
                        "player_count": len(best_cluster),
                        "track_ids": sorted(
                            {
                                int(box["track_id"])
                                for box in best_cluster
                                if box.get("track_id") is not None
                            }
                        ),
                    }
                    last_cluster_ms = timestamp_ms

            if timestamp_ms - last_direction_sample_ms >= 1_000:
                tracked_boxes = [box for box in boxes if box.get("track_id") is not None]
                if tracked_boxes:
                    center_x = sum(float(box["cx"]) for box in tracked_boxes) / len(tracked_boxes)
                    center_y = sum(float(box["cy"]) for box in tracked_boxes) / len(tracked_boxes)
                    if previous_centroid is not None:
                        delta_x = center_x - previous_centroid[1]
                        delta_y = center_y - previous_centroid[2]
                        distance = math.hypot(delta_x, delta_y)
                        if previous_motion is not None:
                            previous_distance = math.hypot(*previous_motion)
                            dot = delta_x * previous_motion[0] + delta_y * previous_motion[1]
                            reversed_direction = (
                                distance >= 0.04
                                and previous_distance >= 0.04
                                and dot <= -0.5 * distance * previous_distance
                            )
                            if reversed_direction and timestamp_ms - last_direction_ms >= 8_000:
                                yield {
                                    "t_ms": timestamp_ms,
                                    "type": "group_direction_change",
                                    "source": "heuristic",
                                    "player_count": len(tracked_boxes),
                                    "track_ids": sorted({int(box["track_id"]) for box in tracked_boxes}),
                                }
                                last_direction_ms = timestamp_ms
                        previous_motion = (delta_x, delta_y) if distance >= 0.015 else None
                    previous_centroid = (timestamp_ms, center_x, center_y)
                else:
                    previous_centroid = None
                    previous_motion = None
                last_direction_sample_ms = timestamp_ms
