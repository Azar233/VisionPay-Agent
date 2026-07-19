"""Dashboard queries for the authenticated user's retail detection activity."""

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.entity.db_models import (
    ChatMessage,
    ChatSession,
    DetectionResult,
    DetectionScene,
    DetectionTask,
)


AGENT_LABELS = {
    "detection": "Detection Agent",
    "dataset": "Dataset Agent",
    "training": "Training Agent",
    "catalog": "Catalog Agent",
    "knowledge": "Knowledge Agent",
}


class DashboardService:
    """Build chart-ready aggregates without owning the database session."""

    @staticmethod
    def _period_summary(db: Session, user_id: int, start: datetime, end: datetime) -> dict:
        row = (
            db.query(
                func.count(DetectionTask.id),
                func.coalesce(func.sum(DetectionTask.total_images), 0),
                func.coalesce(func.sum(DetectionTask.total_objects), 0),
                func.coalesce(func.sum(DetectionTask.total_inference_time), 0.0),
            )
            .filter(
                DetectionTask.user_id == user_id,
                DetectionTask.created_at >= start,
                DetectionTask.created_at < end,
            )
            .one()
        )
        tasks, images, objects, inference_total = row
        images = int(images or 0)
        inference_total = float(inference_total or 0)
        return {
            "total_tasks": int(tasks or 0),
            "total_images": images,
            "total_objects": int(objects or 0),
            # A task may contain many images or sampled video frames. Per-image
            # latency is therefore more meaningful than averaging task totals.
            "avg_inference_time": round(inference_total / images, 2) if images else 0.0,
        }

    @staticmethod
    def get_statistics(db: Session, user_id: int, days: int = 30) -> dict:
        now = datetime.now()
        start = now - timedelta(days=days)
        previous_start = start - timedelta(days=days)
        current = DashboardService._period_summary(db, user_id, start, now)
        previous = DashboardService._period_summary(db, user_id, previous_start, start)

        def growth(key: str) -> float:
            old = previous[key]
            new = current[key]
            if old == 0:
                return 100.0 if new > 0 else 0.0
            return round((new - old) / old * 100, 1)

        return {
            **current,
            "growth": {
                "tasks": growth("total_tasks"),
                "images": growth("total_images"),
                "objects": growth("total_objects"),
                "inference_time": growth("avg_inference_time"),
            },
            "period_days": days,
        }

    @staticmethod
    def get_trend(
        db: Session,
        user_id: int,
        days: int = 30,
        hours: int | None = None,
        bucket_hours: int = 1,
    ) -> dict:
        now = datetime.now()
        if hours is not None:
            bucket_hours = max(1, min(bucket_hours, hours))
            bucket_count = (hours + bucket_hours - 1) // bucket_hours
            last_bucket = now.replace(
                hour=(now.hour // bucket_hours) * bucket_hours,
                minute=0,
                second=0,
                microsecond=0,
            )
            first_hour = last_bucket - timedelta(hours=(bucket_count - 1) * bucket_hours)
            rows = (
                db.query(
                    DetectionTask.created_at,
                    DetectionTask.total_objects,
                    DetectionTask.total_images,
                )
                .filter(
                    DetectionTask.user_id == user_id,
                    DetectionTask.created_at >= first_hour,
                )
                .all()
            )
            by_hour: dict[str, dict] = {}
            for row in rows:
                bucket_time = row.created_at.replace(
                    hour=(row.created_at.hour // bucket_hours) * bucket_hours,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                key = bucket_time.strftime("%Y-%m-%dT%H:00:00")
                bucket = by_hour.setdefault(
                    key,
                    {"date": key, "task_count": 0, "object_count": 0, "image_count": 0},
                )
                bucket["task_count"] += 1
                bucket["object_count"] += int(row.total_objects or 0)
                bucket["image_count"] += int(row.total_images or 0)
            trend = []
            for offset in range(bucket_count):
                key = (first_hour + timedelta(hours=offset * bucket_hours)).strftime("%Y-%m-%dT%H:00:00")
                trend.append(
                    by_hour.get(
                        key,
                        {"date": key, "task_count": 0, "object_count": 0, "image_count": 0},
                    )
                )
            return {
                "trend": trend,
                "period_hours": hours,
                "bucket_hours": bucket_hours,
                "granularity": "hour",
            }

        first_day = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_expr = func.date(DetectionTask.created_at)
        rows = (
            db.query(
                day_expr.label("day"),
                func.count(DetectionTask.id).label("task_count"),
                func.coalesce(func.sum(DetectionTask.total_objects), 0).label("object_count"),
                func.coalesce(func.sum(DetectionTask.total_images), 0).label("image_count"),
            )
            .filter(
                DetectionTask.user_id == user_id,
                DetectionTask.created_at >= first_day,
            )
            .group_by(day_expr)
            .order_by(day_expr)
            .all()
        )
        by_day = {
            str(row.day): {
                "date": str(row.day),
                "task_count": int(row.task_count or 0),
                "object_count": int(row.object_count or 0),
                "image_count": int(row.image_count or 0),
            }
            for row in rows
        }
        trend = []
        for offset in range(days):
            key = (first_day + timedelta(days=offset)).strftime("%Y-%m-%d")
            trend.append(
                by_day.get(
                    key,
                    {"date": key, "task_count": 0, "object_count": 0, "image_count": 0},
                )
            )
        return {"trend": trend, "period_days": days, "granularity": "day"}

    @staticmethod
    def get_model_usage(
        db: Session,
        user_id: int,
        days: int = 30,
        limit: int = 8,
        hours: int | None = None,
        bucket_hours: int = 1,
    ) -> dict:
        """Aggregate persisted LLM activity for one user without exposing prompts."""
        now = datetime.now()
        if hours is not None:
            bucket_hours = max(1, min(bucket_hours, hours))
            bucket_count = (hours + bucket_hours - 1) // bucket_hours
            last_bucket = now.replace(
                hour=(now.hour // bucket_hours) * bucket_hours,
                minute=0,
                second=0,
                microsecond=0,
            )
            period_start = last_bucket - timedelta(hours=(bucket_count - 1) * bucket_hours)
        else:
            bucket_count = days
            period_start = (now - timedelta(days=days - 1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        messages = (
            db.query(ChatMessage)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .filter(
                ChatSession.user_id == user_id,
                ChatMessage.role == "assistant",
                ChatMessage.agent_used.isnot(None),
                ChatMessage.created_at >= period_start,
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .all()
        )

        agent_counts: dict[str, int] = {}
        daily_counts: dict[str, dict] = {}
        recent = []
        total_calls = 0
        total_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0
        latency_values = []
        successful_turns = 0

        for message in messages:
            metadata = message.tool_calls if isinstance(message.tool_calls, dict) else {}
            usage = metadata.get("model_usage") if isinstance(metadata.get("model_usage"), dict) else {}
            try:
                call_count = max(1, int(metadata.get("model_run_count") or 1))
            except (TypeError, ValueError):
                call_count = 1
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            tokens = int(message.tokens_used or usage.get("total_tokens") or 0)
            failed = (message.content or "").startswith(("Agent 处理失败", "请求失败"))
            agent = str(message.agent_used or "unknown")
            model_name = str(metadata.get("model_name") or settings.DEEPSEEK_MODEL)

            total_calls += call_count
            total_tokens += tokens
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            successful_turns += 0 if failed else 1
            if message.latency_ms is not None:
                latency_values.append(int(message.latency_ms))
            # 并行/流水线调用的 agent_used 是逗号拼接的多个子 Agent，
            # 分布统计按子 Agent 拆分：本轮参与的每个子 Agent 各计一次。
            for agent_part in {part.strip() for part in agent.split(",") if part.strip()}:
                agent_counts[agent_part] = agent_counts.get(agent_part, 0) + 1

            if hours is not None:
                bucket_time = message.created_at.replace(
                    hour=(message.created_at.hour // bucket_hours) * bucket_hours,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                bucket_key = bucket_time.strftime("%Y-%m-%dT%H:00:00")
            else:
                bucket_key = message.created_at.strftime("%Y-%m-%d")
            bucket = daily_counts.setdefault(
                bucket_key,
                {"date": bucket_key, "calls": 0, "tokens": 0},
            )
            bucket["calls"] += call_count
            bucket["tokens"] += tokens

            if len(recent) < limit:
                # 并行调用时给出子 Agent 列表，前端按各自颜色竖向排列展示。
                agent_parts = [part.strip() for part in agent.split(",") if part.strip()]
                recent.append(
                    {
                        "id": message.id,
                        "created_at": message.created_at.isoformat(),
                        "model_name": model_name,
                        "agent": agent,
                        "agent_label": AGENT_LABELS.get(agent, agent),
                        "agents": [
                            {"agent": part, "label": AGENT_LABELS.get(part, part)}
                            for part in agent_parts
                        ],
                        "call_count": call_count,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": tokens,
                        "latency_ms": message.latency_ms,
                        "status": "failed" if failed else "completed",
                    }
                )

        trend = []
        for offset in range(bucket_count):
            if hours is not None:
                key = (period_start + timedelta(hours=offset * bucket_hours)).strftime(
                    "%Y-%m-%dT%H:00:00"
                )
            else:
                key = (period_start + timedelta(days=offset)).strftime("%Y-%m-%d")
            trend.append(daily_counts.get(key, {"date": key, "calls": 0, "tokens": 0}))

        turn_count = len(messages)
        return {
            "summary": {
                "total_calls": total_calls,
                "total_turns": turn_count,
                "total_tokens": total_tokens,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "avg_latency_ms": round(sum(latency_values) / len(latency_values)) if latency_values else 0,
                "success_rate": round(successful_turns / turn_count * 100, 1) if turn_count else 0.0,
            },
            "agent_distribution": [
                {
                    "name": AGENT_LABELS.get(agent, agent),
                    "agent": agent,
                    "value": count,
                }
                for agent, count in sorted(agent_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "trend": trend,
            "recent": recent,
            "period_days": days,
            "period_hours": hours,
            "bucket_hours": bucket_hours if hours is not None else None,
            "granularity": "hour" if hours is not None else "day",
        }

    @staticmethod
    def get_class_distribution(db: Session, user_id: int, days: int = 30) -> dict:
        start = datetime.now() - timedelta(days=days)
        display_name = func.coalesce(DetectionResult.class_name_cn, DetectionResult.class_name)
        rows = (
            db.query(display_name.label("name"), func.count(DetectionResult.id).label("count"))
            .join(DetectionTask, DetectionResult.task_id == DetectionTask.id)
            .filter(
                DetectionTask.user_id == user_id,
                DetectionTask.created_at >= start,
            )
            .group_by(display_name)
            .order_by(func.count(DetectionResult.id).desc(), display_name.asc())
            .all()
        )
        return {
            "distribution": [{"name": row.name, "value": int(row.count)} for row in rows],
            "period_days": days,
        }

    @staticmethod
    def get_scene_distribution(db: Session, user_id: int, days: int = 30) -> dict:
        start = datetime.now() - timedelta(days=days)
        rows = (
            db.query(DetectionScene.display_name.label("name"), func.count(DetectionTask.id).label("count"))
            .join(DetectionScene, DetectionTask.scene_id == DetectionScene.id)
            .filter(
                DetectionTask.user_id == user_id,
                DetectionTask.created_at >= start,
            )
            .group_by(DetectionScene.display_name)
            .order_by(func.count(DetectionTask.id).desc(), DetectionScene.display_name.asc())
            .all()
        )
        return {
            "distribution": [{"name": row.name, "value": int(row.count)} for row in rows],
            "period_days": days,
        }

    @staticmethod
    def get_type_distribution(db: Session, user_id: int, days: int = 30) -> dict:
        start = datetime.now() - timedelta(days=days)
        rows = (
            db.query(DetectionTask.task_type.label("name"), func.count(DetectionTask.id).label("count"))
            .filter(
                DetectionTask.user_id == user_id,
                DetectionTask.created_at >= start,
            )
            .group_by(DetectionTask.task_type)
            .order_by(func.count(DetectionTask.id).desc(), DetectionTask.task_type.asc())
            .all()
        )
        labels = {
            "single": "单图识别",
            "batch": "批量识别",
            "folder": "文件夹识别",
            "zip": "ZIP 识别",
            "video": "视频识别",
            "camera": "实时摄像头",
        }
        return {
            "distribution": [
                {"name": labels.get(row.name, row.name), "value": int(row.count)} for row in rows
            ],
            "period_days": days,
        }


dashboard_service = DashboardService()
