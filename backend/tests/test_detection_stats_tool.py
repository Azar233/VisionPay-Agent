import json
from datetime import datetime, timedelta

import pytest

from app.agent.detection_agent import DetectionAgent
from app.config.settings import settings
from app.entity.db_models import DetectionScene, DetectionTask, User


@pytest.fixture
def detection_tasks(db_session, monkeypatch):
    user = User(username="detect_user", email="detect@example.com", hashed_password="x", is_active=True)
    scene = DetectionScene(name="detect-scene", display_name="检测场景", category="retail", class_names=["cola"])
    db_session.add_all([user, scene])
    db_session.flush()
    now = datetime.now()
    db_session.add_all(
        [
            DetectionTask(
                user_id=user.id, scene_id=scene.id, task_type="single", status="completed",
                total_images=1, total_objects=7, created_at=now - timedelta(hours=1),
            ),
            DetectionTask(
                user_id=user.id, scene_id=scene.id, task_type="batch", status="completed",
                total_images=4, total_objects=20, created_at=now - timedelta(hours=2),
            ),
            DetectionTask(
                user_id=user.id, scene_id=scene.id, task_type="single", status="failed",
                total_images=1, total_objects=0, created_at=now - timedelta(days=5),
            ),
        ]
    )
    # 其他用户的任务不应混入统计。
    other = User(username="other_user", email="other@example.com", hashed_password="x", is_active=True)
    db_session.add(other)
    db_session.flush()
    db_session.add(
        DetectionTask(
            user_id=other.id, scene_id=scene.id, task_type="single", status="completed",
            total_images=9, total_objects=99, created_at=now,
        )
    )
    db_session.commit()

    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr("app.database.session.SessionLocal", lambda: db_session)
    return user


def _stats_tool():
    agent = DetectionAgent.__new__(DetectionAgent)
    agent.user_id = None
    agent.scene_id = None
    agent.last_detection_result = None
    executor = agent._build_executor()
    return next(tool for tool in executor.tools if tool.name == "query_detection_stats"), agent


def test_query_detection_stats_aggregates_by_day_and_type(detection_tasks):
    tool, agent = _stats_tool()
    agent.user_id = detection_tasks.id

    result = json.loads(tool.invoke({"days": 1}))

    assert result["total_tasks"] == 2
    assert result["total_images"] == 5
    assert result["total_objects"] == 27
    # 两条任务可能跨零点分桶，按类型汇总验证即可。
    type_counts: dict[str, int] = {}
    for bucket in result["by_day"].values():
        for task_type, count in bucket["types"].items():
            type_counts[task_type] = type_counts.get(task_type, 0) + count
    assert type_counts == {"single": 1, "batch": 1}
    assert len(result["recent_tasks"]) == 2


def test_query_detection_stats_wider_window_includes_older_tasks(detection_tasks):
    tool, agent = _stats_tool()
    agent.user_id = detection_tasks.id

    result = json.loads(tool.invoke({"days": 7}))

    assert result["total_tasks"] == 3
    assert result["total_images"] == 6
    assert result["total_objects"] == 27
    statuses = {task["status"] for task in result["recent_tasks"]}
    assert "failed" in statuses
