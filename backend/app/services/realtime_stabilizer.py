"""Temporal smoothing for noisy frame-by-frame webcam detections."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _iou(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


@dataclass
class _Track:
    track_id: int
    bbox: list[float]
    class_scores: dict[int, float] = field(default_factory=dict)
    class_names: dict[int, str] = field(default_factory=dict)
    confidence_ema: dict[int, float] = field(default_factory=dict)
    hits: int = 1
    misses: int = 0


class RealtimeDetectionStabilizer:
    """Match objects spatially and stabilize their boxes/classes over time."""

    def __init__(
        self,
        *,
        min_hits: int = 2,
        max_misses: int = 2,
        iou_threshold: float = 0.25,
        box_alpha: float = 0.35,
        score_decay: float = 0.82,
        high_confidence: float = 0.75,
        min_class_share: float = 0.45,
    ) -> None:
        self.min_hits = min_hits
        self.max_misses = max_misses
        self.iou_threshold = iou_threshold
        self.box_alpha = box_alpha
        self.score_decay = score_decay
        self.high_confidence = high_confidence
        self.min_class_share = min_class_share
        self._tracks: list[_Track] = []
        self._next_track_id = 1

    def _new_track(self, detection: dict[str, Any]) -> _Track:
        class_id = int(detection["class_id"])
        confidence = float(detection["confidence"])
        track = _Track(
            track_id=self._next_track_id,
            bbox=[float(value) for value in detection["bbox"]],
            class_scores={class_id: confidence},
            class_names={class_id: str(detection["class_name"])},
            confidence_ema={class_id: confidence},
        )
        self._next_track_id += 1
        return track

    def update(self, detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for track in self._tracks:
            track.class_scores = {
                class_id: score * self.score_decay
                for class_id, score in track.class_scores.items()
                if score * self.score_decay >= 0.01
            }

        candidates = []
        for track_index, track in enumerate(self._tracks):
            for detection_index, detection in enumerate(detections):
                overlap = _iou(track.bbox, detection["bbox"])
                if overlap >= self.iou_threshold:
                    candidates.append((overlap, track_index, detection_index))
        candidates.sort(reverse=True)

        matched_tracks: set[int] = set()
        matched_detections: set[int] = set()
        for _overlap, track_index, detection_index in candidates:
            if track_index in matched_tracks or detection_index in matched_detections:
                continue
            track = self._tracks[track_index]
            detection = detections[detection_index]
            class_id = int(detection["class_id"])
            confidence = float(detection["confidence"])
            incoming_bbox = [float(value) for value in detection["bbox"]]
            track.bbox = [
                old * (1 - self.box_alpha) + new * self.box_alpha
                for old, new in zip(track.bbox, incoming_bbox)
            ]
            track.class_scores[class_id] = track.class_scores.get(class_id, 0.0) + confidence
            track.class_names[class_id] = str(detection["class_name"])
            previous_confidence = track.confidence_ema.get(class_id, confidence)
            track.confidence_ema[class_id] = previous_confidence * 0.65 + confidence * 0.35
            track.hits += 1
            track.misses = 0
            matched_tracks.add(track_index)
            matched_detections.add(detection_index)

        for track_index, track in enumerate(self._tracks):
            if track_index not in matched_tracks:
                track.misses += 1
        for detection_index, detection in enumerate(detections):
            if detection_index not in matched_detections:
                self._tracks.append(self._new_track(detection))

        self._tracks = [track for track in self._tracks if track.misses <= self.max_misses]
        stable = []
        for track in self._tracks:
            if not track.class_scores:
                continue
            class_id, top_score = max(track.class_scores.items(), key=lambda item: item[1])
            total_score = sum(track.class_scores.values())
            confidence = track.confidence_ema.get(class_id, 0.0)
            confirmed = track.hits >= self.min_hits or confidence >= self.high_confidence
            if not confirmed or top_score / max(total_score, 0.001) < self.min_class_share:
                continue
            stable.append(
                {
                    "track_id": track.track_id,
                    "class_id": class_id,
                    "class_name": track.class_names[class_id],
                    "confidence": round(confidence, 4),
                    "bbox": [round(value, 2) for value in track.bbox],
                    "stability_hits": track.hits,
                    "persisted": track.misses > 0,
                }
            )
        return stable

