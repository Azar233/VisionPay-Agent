"""Aggregate ByteTrack trajectories into deduplicated counts and lifecycle events.

Shared by offline video tracking and realtime camera scanning. Track IDs are
produced externally (ultralytics ``model.track``); this registry only books
per-track state: confidence-weighted class voting, first/last seen timestamps,
best evidence frame, and a tentative -> confirmed -> expired lifecycle.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TrackRecord:
    """Book-keeping for a single external track ID."""

    track_id: int
    first_frame: int
    first_seen: float
    class_scores: dict[int, float] = field(default_factory=dict)
    class_names: dict[int, str] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    last_frame: int = 0
    last_seen: float = 0.0
    last_confidence: float = 0.0
    last_bbox: list[float] = field(default_factory=list)
    best_confidence: float = 0.0
    best_frame_index: int = 0
    best_timestamp: float = 0.0
    best_bbox: list[float] = field(default_factory=list)
    confirmed: bool = False
    expired: bool = False

    @property
    def class_id(self) -> int:
        """Voted class: argmax of accumulated confidence-weighted scores."""
        return max(self.class_scores.items(), key=lambda item: item[1])[0]

    @property
    def class_name(self) -> str:
        return self.class_names.get(self.class_id, "")

    def summary(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "first_seen": round(self.first_seen, 3),
            "last_seen": round(self.last_seen, 3),
            "duration": round(max(0.0, self.last_seen - self.first_seen), 3),
            "hits": self.hits,
            "best_confidence": round(self.best_confidence, 4),
            "best_frame_index": self.best_frame_index,
            "best_bbox": [round(value, 2) for value in self.best_bbox],
            "expired": self.expired,
        }


class TrackRegistry:
    """Aggregate per-frame track observations into dedup counts.

    Confirmation absorbs the old hysteresis idea: a track counts once it has
    ``min_hits`` observations or a single ``high_confidence`` sighting. A track
    expires after ``max_misses`` consecutive absent frames. Callbacks fire once
    per track on confirmation and expiration.
    """

    def __init__(
        self,
        *,
        min_hits: int = 2,
        max_misses: int = 2,
        min_confidence: float = 0.30,
        high_confidence: float = 0.75,
        on_track_confirmed: Callable[[TrackRecord], None] | None = None,
        on_track_expired: Callable[[TrackRecord], None] | None = None,
    ) -> None:
        self.min_hits = min_hits
        self.max_misses = max_misses
        self.min_confidence = min_confidence
        self.high_confidence = high_confidence
        self.on_track_confirmed = on_track_confirmed
        self.on_track_expired = on_track_expired
        self._records: dict[int, TrackRecord] = {}
        self._peak_simultaneous = 0

    def update(self, frame_index: int, timestamp_sec: float, tracks: list[dict[str, Any]]) -> list[int]:
        """Ingest one frame of ``[{track_id, class_id, class_name, confidence, bbox}]``.

        Returns the track IDs whose best confidence was refreshed by this frame
        (callers use them to capture per-track evidence frames).
        """
        seen_ids: set[int] = set()
        peak_ids: list[int] = []
        for item in tracks:
            track_id = int(item["track_id"])
            class_id = int(item["class_id"])
            confidence = float(item["confidence"])
            bbox = [float(value) for value in item["bbox"]]

            record = self._records.get(track_id)
            if record is None:
                record = TrackRecord(track_id=track_id, first_frame=frame_index, first_seen=timestamp_sec)
                self._records[track_id] = record

            record.hits += 1
            record.misses = 0
            record.last_frame = frame_index
            record.last_seen = timestamp_sec
            record.last_confidence = confidence
            record.last_bbox = bbox
            record.class_scores[class_id] = record.class_scores.get(class_id, 0.0) + confidence
            record.class_names[class_id] = str(item["class_name"])
            if confidence > record.best_confidence:
                record.best_confidence = confidence
                record.best_frame_index = frame_index
                record.best_timestamp = timestamp_sec
                record.best_bbox = bbox
                peak_ids.append(track_id)
            seen_ids.add(track_id)

        newly_confirmed: list[TrackRecord] = []
        for record in self._records.values():
            if record.expired:
                continue
            if record.track_id not in seen_ids:
                record.misses += 1
                if record.misses > self.max_misses:
                    record.expired = True
                    if self.on_track_expired is not None:
                        self.on_track_expired(record)
                continue
            if not record.confirmed and record.best_confidence >= self.min_confidence and (
                record.hits >= self.min_hits or record.best_confidence >= self.high_confidence
            ):
                record.confirmed = True
                newly_confirmed.append(record)

        active_confirmed = sum(
            1 for track_id in seen_ids if self._records[track_id].confirmed
        )
        self._peak_simultaneous = max(self._peak_simultaneous, active_confirmed)

        for record in newly_confirmed:
            if self.on_track_confirmed is not None:
                self.on_track_confirmed(record)
        return peak_ids

    def confirmed_tracks(self, *, include_expired: bool = True) -> list[TrackRecord]:
        return [
            record
            for record in self._records.values()
            if record.confirmed and (include_expired or not record.expired)
        ]

    def active_tracks(self) -> list[dict[str, Any]]:
        """Currently visible confirmed tracks, shaped for realtime display."""
        visible = []
        for record in self._records.values():
            if not record.confirmed or record.expired:
                continue
            visible.append(
                {
                    "track_id": record.track_id,
                    "class_id": record.class_id,
                    "class_name": record.class_name,
                    "confidence": round(record.last_confidence, 4),
                    "bbox": [round(value, 2) for value in record.last_bbox],
                    "stability_hits": record.hits,
                    "persisted": record.misses > 0,
                }
            )
        return visible

    def dedup_class_counts(self) -> dict[str, int]:
        """Unique confirmed tracks per class name."""
        counts: Counter[str] = Counter(record.class_name for record in self.confirmed_tracks())
        return dict(counts)

    @property
    def total_unique(self) -> int:
        return len(self.confirmed_tracks())

    @property
    def peak_simultaneous(self) -> int:
        return self._peak_simultaneous

    def track_summaries(self) -> list[dict[str, Any]]:
        return [
            record.summary()
            for record in sorted(self.confirmed_tracks(), key=lambda item: item.first_seen)
        ]
