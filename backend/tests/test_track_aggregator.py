from app.services.track_aggregator import TrackRegistry


def _track(track_id, class_id, name, confidence, bbox=None):
    return {
        "track_id": track_id,
        "class_id": class_id,
        "class_name": name,
        "confidence": confidence,
        "bbox": bbox or [10, 10, 100, 100],
    }


def test_registry_confirms_after_min_hits_and_dedups_by_track():
    registry = TrackRegistry(min_hits=2)

    registry.update(0, 0.0, [_track(1, 1, "drink", 0.55)])
    assert registry.total_unique == 0

    registry.update(1, 0.5, [_track(1, 1, "drink", 0.58)])
    registry.update(2, 1.0, [_track(1, 1, "drink", 0.60)])

    assert registry.total_unique == 1
    assert registry.dedup_class_counts() == {"drink": 1}


def test_registry_high_confidence_fast_confirms_single_sighting():
    registry = TrackRegistry(min_hits=2, high_confidence=0.75)

    registry.update(0, 0.0, [_track(1, 1, "drink", 0.82)])

    assert registry.total_unique == 1


def test_registry_votes_class_by_accumulated_confidence():
    registry = TrackRegistry(min_hits=2)
    registry.update(0, 0.0, [_track(1, 2, "chocolate", 0.40)])
    registry.update(1, 0.5, [_track(1, 1, "drink", 0.65)])
    registry.update(2, 1.0, [_track(1, 1, "drink", 0.70)])

    summary = registry.track_summaries()[0]
    assert summary["class_id"] == 1
    assert summary["class_name"] == "drink"


def test_registry_expires_after_max_misses_and_fires_callbacks():
    events = []
    registry = TrackRegistry(
        min_hits=1,
        max_misses=2,
        on_track_confirmed=lambda record: events.append(("confirmed", record.track_id)),
        on_track_expired=lambda record: events.append(("expired", record.track_id)),
    )

    registry.update(0, 0.0, [_track(1, 1, "drink", 0.60)])
    registry.update(1, 0.5, [])
    registry.update(2, 1.0, [])
    assert [record.track_id for record in registry.confirmed_tracks(include_expired=False)] == [1]

    registry.update(3, 1.5, [])

    assert events == [("confirmed", 1), ("expired", 1)]
    assert registry.confirmed_tracks(include_expired=False) == []
    # 过期轨迹仍计入去重总数（真实出现过的商品）。
    assert registry.total_unique == 1


def test_registry_active_tracks_keeps_box_during_short_misses():
    registry = TrackRegistry(min_hits=1, max_misses=2)
    registry.update(0, 0.0, [_track(1, 1, "drink", 0.60)])

    registry.update(1, 0.5, [])
    visible = registry.active_tracks()

    assert len(visible) == 1
    assert visible[0]["persisted"] is True

    registry.update(2, 1.0, [])
    registry.update(3, 1.5, [])
    assert registry.active_tracks() == []


def test_registry_peak_simultaneous_counts_confirmed_per_frame():
    registry = TrackRegistry(min_hits=1)
    registry.update(0, 0.0, [_track(1, 1, "drink", 0.6), _track(2, 1, "drink", 0.6)])
    registry.update(1, 0.5, [_track(1, 1, "drink", 0.6)])
    registry.update(2, 1.0, [_track(1, 1, "drink", 0.6), _track(3, 2, "chocolate", 0.6)])

    assert registry.peak_simultaneous == 2
    assert registry.total_unique == 3


def test_registry_summaries_report_first_last_seen_and_best_frame():
    registry = TrackRegistry(min_hits=1)
    registry.update(2, 1.0, [_track(5, 1, "drink", 0.50)])
    registry.update(4, 2.0, [_track(5, 1, "drink", 0.90, [20, 20, 80, 80])])
    registry.update(6, 3.0, [_track(5, 1, "drink", 0.60)])

    summary = registry.track_summaries()[0]
    assert summary["track_id"] == 5
    assert summary["first_seen"] == 1.0
    assert summary["last_seen"] == 3.0
    assert summary["duration"] == 2.0
    assert summary["best_confidence"] == 0.9
    assert summary["best_frame_index"] == 4
    assert summary["best_bbox"] == [20, 20, 80, 80]


def test_registry_separate_ids_never_merge_even_with_same_class():
    registry = TrackRegistry(min_hits=1)
    frame = [_track(1, 1, "drink", 0.6), _track(2, 1, "drink", 0.6), _track(3, 1, "drink", 0.6)]
    registry.update(0, 0.0, frame)

    assert registry.dedup_class_counts() == {"drink": 3}
