from app.services.realtime_stabilizer import RealtimeDetectionStabilizer


def _detection(class_id, name, confidence, bbox=None):
    return {
        "class_id": class_id,
        "class_name": name,
        "confidence": confidence,
        "bbox": bbox or [10, 10, 100, 100],
    }


def test_stabilizer_requires_repeated_detection_and_votes_for_class():
    stabilizer = RealtimeDetectionStabilizer(min_hits=2)

    assert stabilizer.update([_detection(1, "drink", 0.55)]) == []
    stable = stabilizer.update([_detection(2, "chocolate", 0.40, [12, 11, 102, 101])])

    assert len(stable) == 1
    assert stable[0]["class_id"] == 1
    assert stable[0]["class_name"] == "drink"
    assert stable[0]["stability_hits"] == 2
    assert stable[0]["bbox"] != [12, 11, 102, 101]


def test_stabilizer_persists_short_misses_then_removes_track():
    stabilizer = RealtimeDetectionStabilizer(min_hits=2, max_misses=2)
    stabilizer.update([_detection(1, "drink", 0.60)])
    assert stabilizer.update([_detection(1, "drink", 0.58)])

    first_miss = stabilizer.update([])
    second_miss = stabilizer.update([])
    expired = stabilizer.update([])

    assert first_miss[0]["persisted"] is True
    assert second_miss[0]["persisted"] is True
    assert expired == []


def test_stabilizer_keeps_spatially_separate_objects():
    stabilizer = RealtimeDetectionStabilizer(min_hits=2)
    frame = [
        _detection(1, "drink", 0.7, [0, 0, 50, 50]),
        _detection(1, "drink", 0.68, [100, 100, 160, 160]),
    ]
    stabilizer.update(frame)
    stable = stabilizer.update(frame)

    assert len(stable) == 2
    assert {item["track_id"] for item in stable} == {1, 2}
