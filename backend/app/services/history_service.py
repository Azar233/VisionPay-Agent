"""Unified detection, Agent-call and model-lifecycle history queries."""

import json
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import String, cast, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.entity.db_models import (
    AgentPendingOperation,
    ChatMessage,
    ChatSession,
    DetectionResult,
    DetectionScene,
    DetectionTask,
    ModelVersion,
    OperationLog,
    TrainingTask,
    User,
)


AGENT_LABELS = {
    "detection": "Detection Agent",
    "dataset": "Dataset Agent",
    "training": "Training Agent",
    "catalog": "Catalog Agent",
    "knowledge": "Knowledge Agent",
}

TOOL_LABELS = {
    "detect_single_product_image": "执行单图商品检测",
    "detect_multiple_product_images": "执行批量商品检测",
    "detect_zip_product_images": "执行 ZIP 商品检测",
    "detect_product_video": "执行视频商品检测",
    "list_dataset_versions": "查询数据集版本",
    "get_current_dataset_version": "查询当前数据集",
    "get_dataset_version_detail": "查询数据集详情",
    "prepare_add_samples_handoff": "发起样品标注交接",
    "preview_derive_dataset_version": "预览派生数据集",
    "preview_freeze_dataset_version": "预览冻结数据集",
    "preview_archive_dataset_version": "预览归档数据集",
    "preview_delete_product_samples": "预览删除商品样品",
    "preview_delete_dataset_draft": "预览删除数据集草稿",
    "list_training_tasks": "查询训练任务",
    "get_training_status": "查询训练状态",
    "get_training_metrics": "查询训练指标",
    "preview_start_training": "预览启动训练",
    "preview_stop_training": "预览停止训练",
    "preview_set_default_model": "预览切换默认模型",
    "list_product_prices": "查询商品价目表",
    "preview_update_product_price": "预览商品改价",
    "preview_clear_product_price": "预览清除价格",
    "get_platform_agent_capabilities": "查询平台 Agent 能力",
    "search_management_knowledge": "检索管理知识库",
    "search_fault_cases": "检索故障案例",
    "remember_management_preference": "保存管理偏好",
    "recall_management_memory": "召回管理偏好",
    "request_user_input_form": "请求补充任务参数",
}

MODEL_ACTION_LABELS = {
    "set_default": "设为默认检测模型",
    "unset_default": "取消默认检测模型",
    "auto_set_default": "自动接替默认检测模型",
    "archive": "归档模型",
    "validate": "执行模型评估",
    "export": "导出模型产物",
    "download": "下载模型权重",
}


class HistoryService:
    @staticmethod
    def _date_bounds(start_date: date | None, end_date: date | None):
        start = datetime.combine(start_date, time.min) if start_date else None
        end = (
            datetime.combine(end_date + timedelta(days=1), time.min)
            if end_date
            else None
        )
        return start, end

    @staticmethod
    def list_tasks(
        db: Session,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = 10,
        task_type: str | None = None,
        status: str | None = None,
        scene_id: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        keyword: str | None = None,
    ) -> dict:
        query = (
            db.query(DetectionTask)
            .join(DetectionScene, DetectionTask.scene_id == DetectionScene.id)
            .options(joinedload(DetectionTask.scene))
            .filter(DetectionTask.user_id == user_id)
        )
        if task_type:
            query = query.filter(DetectionTask.task_type == task_type)
        if status:
            query = query.filter(DetectionTask.status == status)
        if scene_id is not None:
            query = query.filter(DetectionTask.scene_id == scene_id)
        if start_date:
            query = query.filter(DetectionTask.created_at >= datetime.combine(start_date, time.min))
        if end_date:
            query = query.filter(
                DetectionTask.created_at < datetime.combine(end_date + timedelta(days=1), time.min)
            )
        keyword = (keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            query = query.filter(
                or_(
                    cast(DetectionTask.id, String).ilike(pattern),
                    DetectionScene.name.ilike(pattern),
                    DetectionScene.display_name.ilike(pattern),
                )
            )

        total = query.count()
        tasks = (
            query.order_by(desc(DetectionTask.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [HistoryService._task_dict(task) for task in tasks],
        }

    @staticmethod
    def _task_dict(task: DetectionTask) -> dict:
        return {
            "id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "scene_id": task.scene_id,
            "scene_name": task.scene.display_name if task.scene else None,
            "total_images": task.total_images or 0,
            "total_objects": task.total_objects or 0,
            "total_inference_time": round(task.total_inference_time or 0, 2),
            "avg_inference_time": round(
                (task.total_inference_time or 0) / task.total_images, 2
            ) if task.total_images else 0.0,
            "conf_threshold": task.conf_threshold,
            "iou_threshold": task.iou_threshold,
            "error_message": task.error_message,
            "analysis_report": task.analysis_report,
            "analysis_suggestion": task.analysis_suggestion,
            "risk_level": task.risk_level,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    @staticmethod
    def get_task_detail(db: Session, user_id: int, task_id: int) -> dict | None:
        task = (
            db.query(DetectionTask)
            .options(joinedload(DetectionTask.scene))
            .filter(DetectionTask.id == task_id, DetectionTask.user_id == user_id)
            .first()
        )
        if not task:
            return None
        results = (
            db.query(DetectionResult)
            .filter(DetectionResult.task_id == task_id)
            .order_by(DetectionResult.id)
            .all()
        )
        class_counts: dict[str, int] = {}
        result_items = []
        for result in results:
            name = result.class_name_cn or result.class_name
            class_counts[name] = class_counts.get(name, 0) + 1
            result_items.append(
                {
                    "id": result.id,
                    "class_name": result.class_name,
                    "class_name_cn": result.class_name_cn,
                    "class_id": result.class_id,
                    "confidence": round(result.confidence, 4),
                    "bbox": result.bbox,
                    "image_path": result.image_path,
                    "annotated_image_url": result.annotated_image_url,
                    "inference_time": round(result.inference_time, 2)
                    if result.inference_time is not None
                    else None,
                    "image_width": result.image_width,
                    "image_height": result.image_height,
                }
            )
        return {
            "task": HistoryService._task_dict(task),
            "class_counts": class_counts,
            "results": result_items,
        }

    @staticmethod
    def delete_task(db: Session, user_id: int, task_id: int) -> bool:
        task = (
            db.query(DetectionTask)
            .filter(DetectionTask.id == task_id, DetectionTask.user_id == user_id)
            .first()
        )
        if not task:
            return False
        db.delete(task)
        db.commit()
        return True

    @staticmethod
    def get_summary(db: Session, user_id: int) -> dict:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        total = (
            db.query(func.count(DetectionTask.id))
            .filter(DetectionTask.user_id == user_id)
            .scalar()
            or 0
        )
        today_count = (
            db.query(func.count(DetectionTask.id))
            .filter(DetectionTask.user_id == user_id, DetectionTask.created_at >= today)
            .scalar()
            or 0
        )
        rows = (
            db.query(DetectionTask.status, func.count(DetectionTask.id))
            .filter(DetectionTask.user_id == user_id)
            .group_by(DetectionTask.status)
            .all()
        )
        status_counts = {name: 0 for name in ("completed", "processing", "failed", "pending")}
        status_counts.update({status: int(count) for status, count in rows})
        return {
            "total_tasks": int(total),
            "today_tasks": int(today_count),
            "status_counts": status_counts,
        }

    @staticmethod
    def list_scenes(db: Session) -> list[dict]:
        scenes = (
            db.query(DetectionScene)
            .filter(DetectionScene.is_active.is_(True))
            .order_by(DetectionScene.display_name)
            .all()
        )
        return [
            {
                "id": scene.id,
                "name": scene.name,
                "display_name": scene.display_name,
                "category": scene.category,
            }
            for scene in scenes
        ]

    @staticmethod
    def _agent_activity(db: Session, message: ChatMessage) -> dict[str, Any]:
        user_message = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == message.session_id,
                ChatMessage.role == "user",
                ChatMessage.id < message.id,
            )
            .order_by(ChatMessage.id.desc())
            .first()
        )
        assistant_meta = message.tool_calls if isinstance(message.tool_calls, dict) else {}
        user_meta = (
            user_message.tool_calls
            if user_message is not None and isinstance(user_message.tool_calls, dict)
            else {}
        )
        confirmation = assistant_meta.get("confirmation") or {}
        handoff = assistant_meta.get("handoff") or {}
        input_form = assistant_meta.get("input_form") or {}
        tool = str(assistant_meta.get("tool") or "")
        tools = assistant_meta.get("tools") or ([tool] if tool else [])
        routing = assistant_meta.get("routing") or user_meta.get("routing") or {}
        action = str(
            confirmation.get("action")
            or handoff.get("action")
            or input_form.get("purpose")
            or tool
            or "conversation"
        )
        action_label = TOOL_LABELS.get(tool)
        if not action_label and confirmation.get("impact", {}).get("title"):
            action_label = str(confirmation["impact"]["title"])
        if not action_label and handoff:
            action_label = "发起人工页面交接"
        if not action_label and input_form:
            action_label = "请求补充任务参数"
        if not action_label:
            action_label = "分析并回答用户请求"
        content = message.content or ""
        failed = content.startswith("Agent 处理失败") or content.startswith("请求失败")
        attachments = user_meta.get("attachments") or []
        return {
            "id": message.id,
            "session_uuid": message.session.session_uuid,
            "session_title": message.session.title,
            "agent": message.agent_used,
            "agent_label": AGENT_LABELS.get(message.agent_used, message.agent_used),
            "action": action,
            "action_label": action_label,
            "tool": tool or None,
            "tools": tools,
            "routing": {
                key: routing.get(key)
                for key in ("method", "confidence", "reason")
                if routing.get(key) is not None
            },
            "user_request": user_message.content if user_message else "",
            "response": content,
            "attachments": attachments,
            "attachment_count": len(attachments),
            "has_detection_result": bool(message.tool_result),
            "status": "failed" if failed else "completed",
            "tokens_used": message.tokens_used,
            "latency_ms": message.latency_ms,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    @classmethod
    def list_agent_calls(
        cls,
        db: Session,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = 10,
        agent: str | None = None,
        keyword: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        query = (
            db.query(ChatMessage)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .options(joinedload(ChatMessage.session))
            .filter(
                ChatSession.user_id == user_id,
                ChatMessage.role == "assistant",
                ChatMessage.agent_used.isnot(None),
            )
        )
        if agent:
            query = query.filter(ChatMessage.agent_used == agent)
        start, end = cls._date_bounds(start_date, end_date)
        if start:
            query = query.filter(ChatMessage.created_at >= start)
        if end:
            query = query.filter(ChatMessage.created_at < end)
        keyword = (keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            matching_sessions = db.query(ChatMessage.session_id).filter(
                ChatMessage.role == "user",
                ChatMessage.content.ilike(pattern),
            )
            query = query.filter(
                or_(
                    ChatMessage.content.ilike(pattern),
                    ChatMessage.agent_used.ilike(pattern),
                    ChatSession.title.ilike(pattern),
                    ChatSession.id.in_(matching_sessions),
                )
            )
        total = query.count()
        rows = (
            query.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [cls._agent_activity(db, row) for row in rows],
        }

    @classmethod
    def get_agent_call(cls, db: Session, user_id: int, message_id: int) -> dict | None:
        message = (
            db.query(ChatMessage)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .options(joinedload(ChatMessage.session))
            .filter(
                ChatMessage.id == message_id,
                ChatMessage.role == "assistant",
                ChatSession.user_id == user_id,
            )
            .first()
        )
        return cls._agent_activity(db, message) if message else None

    @staticmethod
    def _model_origin(model: ModelVersion) -> str:
        if model.training_task_id is not None:
            return "training"
        if model.model_name == "backend/best.pt":
            return "builtin"
        return "imported"

    @classmethod
    def _model_dict(cls, db: Session, model: ModelVersion) -> dict[str, Any]:
        direct_operations = (
            db.query(OperationLog)
            .filter(
                OperationLog.module == "model",
                OperationLog.target_type == "model_version",
                OperationLog.target_id == str(model.id),
            )
            .all()
        )
        agent_operations = (
            db.query(AgentPendingOperation)
            .filter(
                AgentPendingOperation.status == "completed",
                AgentPendingOperation.action == "training.set_default_model",
            )
            .all()
        )
        matching_agent_operations = [
            operation
            for operation in agent_operations
            if int((operation.parameters or {}).get("model_version_id") or 0) == model.id
        ]
        fallback_agent_operations = []
        for operation in matching_agent_operations:
            event_time = operation.executed_at or operation.updated_at
            duplicate = any(
                log.action == "set_default"
                and log.created_at is not None
                and event_time is not None
                and abs((log.created_at - event_time).total_seconds()) <= 2
                for log in direct_operations
            )
            if not duplicate:
                fallback_agent_operations.append(operation)
        operation_times = [
            value
            for value in (
                [log.created_at for log in direct_operations]
                + [operation.executed_at or operation.updated_at for operation in fallback_agent_operations]
            )
            if value is not None
        ]
        latest_operation_at = max(operation_times) if operation_times else None
        task = model.training_task
        return {
            "id": model.id,
            "scene_id": model.scene_id,
            "scene_name": getattr(model.scene, "display_name", None)
            or getattr(model.scene, "name", None),
            "version": model.version,
            "model_name": model.model_name,
            "model_type": model.model_type,
            "status": model.status,
            "is_default": bool(model.is_default),
            "origin": cls._model_origin(model),
            "training_task_id": model.training_task_id,
            "training_task_uuid": getattr(task, "task_uuid", None),
            "dataset_version_id": model.dataset_version_id,
            "dataset_version": getattr(model.dataset_version, "version", None),
            "created_by": getattr(getattr(task, "user", None), "username", None),
            "description": model.description,
            "file_size": model.file_size,
            "map50": model.map50,
            "map50_95": model.map50_95,
            "precision": model.precision,
            "recall": model.recall,
            "operation_count": len(direct_operations) + len(fallback_agent_operations),
            "latest_operation_at": latest_operation_at.isoformat()
            if latest_operation_at
            else None,
            "created_at": model.created_at.isoformat() if model.created_at else None,
        }

    @classmethod
    def list_models(
        cls,
        db: Session,
        *,
        page: int = 1,
        page_size: int = 10,
        scene_id: int | None = None,
        status: str | None = None,
        origin: str | None = None,
        keyword: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        query = db.query(ModelVersion).options(
            joinedload(ModelVersion.scene),
            joinedload(ModelVersion.dataset_version),
            joinedload(ModelVersion.training_task).joinedload(TrainingTask.user),
        )
        if scene_id is not None:
            query = query.filter(ModelVersion.scene_id == scene_id)
        if status:
            query = query.filter(ModelVersion.status == status)
        start, end = cls._date_bounds(start_date, end_date)
        if start:
            query = query.filter(ModelVersion.created_at >= start)
        if end:
            query = query.filter(ModelVersion.created_at < end)
        keyword = (keyword or "").strip()
        if keyword:
            pattern = f"%{keyword}%"
            query = query.join(DetectionScene).filter(
                or_(
                    ModelVersion.version.ilike(pattern),
                    ModelVersion.model_name.ilike(pattern),
                    DetectionScene.name.ilike(pattern),
                    DetectionScene.display_name.ilike(pattern),
                )
            )
        total_before_origin = query.count()
        if origin:
            # Origin is derived from existing columns and is intentionally
            # filtered in Python to keep the rule identical to serialization.
            matching = [model for model in query.all() if cls._model_origin(model) == origin]
            total = len(matching)
            rows = matching[(page - 1) * page_size : page * page_size]
        else:
            total = total_before_origin
            rows = (
                query.order_by(ModelVersion.created_at.desc(), ModelVersion.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "items": [cls._model_dict(db, row) for row in rows],
        }

    @classmethod
    def get_model_history(cls, db: Session, model_id: int) -> dict | None:
        model = (
            db.query(ModelVersion)
            .options(
                joinedload(ModelVersion.scene),
                joinedload(ModelVersion.dataset_version),
                joinedload(ModelVersion.training_task).joinedload(TrainingTask.user),
            )
            .filter(ModelVersion.id == model_id)
            .first()
        )
        if model is None:
            return None
        origin = cls._model_origin(model)
        created_label = {
            "training": "训练完成并登记模型",
            "imported": "导入并创建模型版本",
            "builtin": "登记系统内置模型",
        }.get(origin, "创建模型版本")
        events: list[dict[str, Any]] = [
            {
                "id": f"created-{model.id}",
                "action": "created",
                "action_label": created_label,
                "status": "success",
                "actor": cls._model_dict(db, model).get("created_by") or "系统",
                "description": model.description or "模型版本已登记。",
                "created_at": model.created_at.isoformat() if model.created_at else None,
                "source": "model_version",
            }
        ]
        logs = (
            db.query(OperationLog)
            .filter(
                OperationLog.module == "model",
                OperationLog.target_type == "model_version",
                OperationLog.target_id == str(model.id),
            )
            .order_by(OperationLog.created_at.desc())
            .all()
        )
        for log in logs:
            detail: Any = log.description
            try:
                parsed = json.loads(log.description or "")
                detail = parsed.get("detail") or parsed.get("description") or log.description
            except (TypeError, json.JSONDecodeError):
                pass
            events.append(
                {
                    "id": f"log-{log.id}",
                    "action": log.action,
                    "action_label": MODEL_ACTION_LABELS.get(log.action, log.action),
                    "status": log.status,
                    "actor": log.username or "系统",
                    "description": detail,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                    "source": "operation_log",
                }
            )
        agent_operations = (
            db.query(AgentPendingOperation)
            .filter(
                AgentPendingOperation.status == "completed",
                AgentPendingOperation.action == "training.set_default_model",
            )
            .order_by(AgentPendingOperation.executed_at.desc())
            .all()
        )
        logged_times = {
            event["created_at"][:19]
            for event in events
            if event["action"] == "set_default" and event.get("created_at")
        }
        for operation in agent_operations:
            if int((operation.parameters or {}).get("model_version_id") or 0) != model.id:
                continue
            event_time = operation.executed_at or operation.updated_at
            event_iso = event_time.isoformat() if event_time else None
            if event_iso and event_iso[:19] in logged_times:
                continue
            actor = db.query(User.username).filter(User.id == operation.user_id).scalar()
            events.append(
                {
                    "id": f"agent-operation-{operation.id}",
                    "action": "set_default",
                    "action_label": "通过 Training Agent 设为默认模型",
                    "status": "success",
                    "actor": actor or f"用户 #{operation.user_id}",
                    "description": (operation.impact or {}).get("summary")
                    or "用户确认后由 Training Agent 执行。",
                    "created_at": event_iso,
                    "source": "agent_operation",
                }
            )
        events.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return {"model": cls._model_dict(db, model), "events": events}

    @staticmethod
    def get_unified_summary(db: Session, user_id: int) -> dict[str, int]:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        agent_calls = (
            db.query(func.count(ChatMessage.id))
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .filter(
                ChatSession.user_id == user_id,
                ChatMessage.role == "assistant",
                ChatMessage.agent_used.isnot(None),
            )
            .scalar()
            or 0
        )
        today_agent_calls = (
            db.query(func.count(ChatMessage.id))
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .filter(
                ChatSession.user_id == user_id,
                ChatMessage.role == "assistant",
                ChatMessage.agent_used.isnot(None),
                ChatMessage.created_at >= today,
            )
            .scalar()
            or 0
        )
        return {
            "detection_tasks": int(
                db.query(func.count(DetectionTask.id))
                .filter(DetectionTask.user_id == user_id)
                .scalar()
                or 0
            ),
            "agent_calls": int(agent_calls),
            "today_agent_calls": int(today_agent_calls),
            "models": int(db.query(func.count(ModelVersion.id)).scalar() or 0),
            "active_models": int(
                db.query(func.count(ModelVersion.id))
                .filter(ModelVersion.status == "active")
                .scalar()
                or 0
            ),
        }


history_service = HistoryService()
