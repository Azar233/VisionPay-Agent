"""Read-only Training Agent tools; training may execute on another machine."""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from app.agent.tools.common import json_text
from app.database.session import SessionLocal
from app.entity.db_models import TrainingTask
from app.training.training_service import training_service
from app.services.agent_confirmation_service import agent_confirmation_service


def build_training_tools(user_id: int, session_uuid: str) -> list:
    def _preview(action: str, parameters: dict) -> str:
        db = SessionLocal()
        try:
            view = agent_confirmation_service.create_preview(
                db,
                user_id=user_id,
                username=None,
                session_uuid=session_uuid,
                action=action,
                parameters=parameters,
            )
            view.pop("confirmation_token", None)
            return json_text(view)
        finally:
            db.close()

    def list_training_tasks() -> str:
        """列出当前经营者的训练任务、远端/离线训练状态和关键配置。"""
        db = SessionLocal()
        try:
            return json_text({"items": training_service.get_task_list(db, user_id=user_id)})
        finally:
            db.close()

    def get_training_status(task_id: int) -> str:
        """查询当前经营者指定训练任务的进度和最新指标。"""
        db = SessionLocal()
        try:
            owned = db.query(TrainingTask).filter(
                TrainingTask.id == task_id, TrainingTask.user_id == user_id
            ).first()
            if owned is None:
                return json_text({"error": "训练任务不存在或无权访问"})
            return json_text(training_service.get_training_status(db, task_id))
        finally:
            db.close()

    def get_training_metrics(task_id: int) -> str:
        """查询当前经营者指定训练任务的逐 epoch 指标。"""
        db = SessionLocal()
        try:
            owned = db.query(TrainingTask).filter(
                TrainingTask.id == task_id, TrainingTask.user_id == user_id
            ).first()
            if owned is None:
                return json_text({"error": "训练任务不存在或无权访问"})
            metrics = training_service.get_training_metrics(db, task_id)
            return json_text({"task_id": task_id, "metrics": metrics})
        finally:
            db.close()

    def preview_start_training(
        scene_id: int,
        dataset_version_id: int,
        model_name: str = "yolov11n",
        epochs: int = 100,
        img_size: int = 640,
        batch_size: int = 16,
        device: str = "0",
        optimizer: str = "SGD",
        lr0: float = 0.01,
    ) -> str:
        """预览训练数据集和完整参数，生成一次性待确认操作；不会直接启动训练。"""
        return _preview(
            "training.start",
            {
                "scene_id": scene_id,
                "dataset_version_id": dataset_version_id,
                "model_name": model_name,
                "epochs": epochs,
                "img_size": img_size,
                "batch_size": batch_size,
                "device": device,
                "optimizer": optimizer,
                "lr0": lr0,
            },
        )

    def preview_stop_training(task_id: int) -> str:
        """预览停止训练的当前进度和损失，生成一次性待确认操作。"""
        return _preview("training.stop", {"task_id": task_id})

    def preview_set_default_model(model_version_id: int) -> str:
        """预览新旧默认模型、数据集来源和指标，生成高风险一次性待确认操作。"""
        return _preview(
            "training.set_default_model", {"model_version_id": model_version_id}
        )

    return [
        StructuredTool.from_function(list_training_tasks, name="list_training_tasks"),
        StructuredTool.from_function(get_training_status, name="get_training_status"),
        StructuredTool.from_function(get_training_metrics, name="get_training_metrics"),
        StructuredTool.from_function(preview_start_training, name="preview_start_training"),
        StructuredTool.from_function(preview_stop_training, name="preview_stop_training"),
        StructuredTool.from_function(
            preview_set_default_model, name="preview_set_default_model"
        ),
    ]
