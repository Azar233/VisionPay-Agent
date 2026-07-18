"""DeepSeek-powered retail detection agent with request-scoped tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncGenerator

from app.config.settings import settings
from app.agent.custom_instructions import (
    CUSTOM_INSTRUCTIONS_PROMPT,
    render_custom_instructions,
)
from app.agent.usage import usage_metadata
from app.core.logger import get_logger
from app.agent.tools import build_interaction_tools
from app.services.detection_service import detection_service, result_to_json

logger = get_logger(__name__)


class AgentConfigurationError(RuntimeError):
    """Raised when the DeepSeek agent is not configured."""


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


class DetectionAgent:
    """One request-scoped Agent so user/model/tool state never leaks between users."""

    def __init__(self, *, user_id: int, scene_id: int | None = None):
        if not settings.DEEPSEEK_API_KEY or settings.DEEPSEEK_API_KEY.startswith("sk-your-"):
            raise AgentConfigurationError(
                "DeepSeek 尚未配置，请在 backend/.env 设置 DEEPSEEK_API_KEY 和 DEEPSEEK_MODEL"
            )
        self.user_id = user_id
        self.scene_id = scene_id
        self.last_detection_result: dict[str, Any] | None = None
        self.executor = self._build_executor()

    @staticmethod
    def _allowed_attachment(path_value: str) -> Path:
        root = Path(settings.DETECTION_UPLOAD_DIR).resolve()
        path = Path(path_value).resolve()
        if root != path and root not in path.parents:
            raise ValueError("附件路径不在允许的上传目录中")
        if not path.is_file():
            raise ValueError("附件文件不存在或已失效")
        return path

    def _build_executor(self):
        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        from langchain_core.tools import StructuredTool
        from langchain_openai import ChatOpenAI

        def single(image_path: str, confidence: float = 0.25) -> str:
            """检测一张零售商品图片，返回商品数量、类别和置信度统计。"""
            path = self._allowed_attachment(image_path)
            self.last_detection_result = detection_service.detect_single(
                path,
                user_id=self.user_id,
                scene_id=self.scene_id,
                conf=confidence,
            )
            return result_to_json(self.last_detection_result)

        def batch(image_paths: list[str], confidence: float = 0.25) -> str:
            """批量检测多张零售商品图片，适合多个已上传图片附件。"""
            paths = [self._allowed_attachment(path) for path in image_paths]
            self.last_detection_result = detection_service.detect_batch(
                paths,
                user_id=self.user_id,
                scene_id=self.scene_id,
                conf=confidence,
            )
            return result_to_json(self.last_detection_result)

        def zip_images(zip_path: str, confidence: float = 0.25) -> str:
            """解压并检测 ZIP 中的零售商品图片。"""
            path = self._allowed_attachment(zip_path)
            self.last_detection_result = detection_service.detect_zip(
                path,
                user_id=self.user_id,
                scene_id=self.scene_id,
                conf=confidence,
            )
            return result_to_json(self.last_detection_result)

        def video(video_path: str, confidence: float = 0.25) -> str:
            """抽取视频关键帧并检测零售商品，返回时长、帧数和类别统计。"""
            path = self._allowed_attachment(video_path)
            self.last_detection_result = detection_service.detect_video(
                path,
                user_id=self.user_id,
                scene_id=self.scene_id,
                conf=confidence,
                frame_sample_rate=settings.VIDEO_FRAME_SAMPLE_RATE,
                max_frames=settings.VIDEO_MAX_KEY_FRAMES,
            )
            return result_to_json(self.last_detection_result)

        def list_system_users(keyword: str = "") -> str:
            """管理员查询系统用户，可按用户名或邮箱关键词筛选，也可用于查询管理员。"""
            from app.database.session import SessionLocal
            from app.services.user_service import user_service

            db = SessionLocal()
            try:
                requester = user_service.get_user_by_id(db, self.user_id)
                if not user_service.is_admin(requester):
                    return json.dumps(
                        {"error": "仅管理员可查询系统用户与权限信息"},
                        ensure_ascii=False,
                    )
                result = user_service.list_users(
                    db,
                    page=1,
                    page_size=100,
                    keyword=keyword or None,
                )
                return json.dumps(result, ensure_ascii=False)
            finally:
                db.close()

        def query_detection_stats(days: int = 1) -> str:
            """查询当前用户的检测任务统计：任务数、图片数、商品实例数和按天/类型分布，适合"今天检测了多少任务/识别了多少东西"类问题。"""
            from datetime import datetime, timedelta

            from app.database.session import SessionLocal
            from app.entity.db_models import DetectionTask

            db = SessionLocal()
            try:
                days = max(1, min(int(days or 1), 90))
                since = datetime.now() - timedelta(days=days)
                tasks = (
                    db.query(DetectionTask)
                    .filter(
                        DetectionTask.user_id == self.user_id,
                        DetectionTask.created_at >= since,
                    )
                    .order_by(DetectionTask.created_at.desc())
                    .all()
                )
                by_day: dict[str, dict] = {}
                for task in tasks:
                    day = task.created_at.strftime("%Y-%m-%d") if task.created_at else "unknown"
                    bucket = by_day.setdefault(
                        day, {"task_count": 0, "images": 0, "objects": 0, "types": {}}
                    )
                    bucket["task_count"] += 1
                    bucket["images"] += int(task.total_images or 0)
                    bucket["objects"] += int(task.total_objects or 0)
                    task_type = str(task.task_type or "unknown")
                    bucket["types"][task_type] = bucket["types"].get(task_type, 0) + 1
                recent = [
                    {
                        "id": task.id,
                        "task_type": task.task_type,
                        "status": task.status,
                        "images": int(task.total_images or 0),
                        "objects": int(task.total_objects or 0),
                        "created_at": task.created_at.strftime("%Y-%m-%d %H:%M")
                        if task.created_at
                        else None,
                    }
                    for task in tasks[:5]
                ]
                return json.dumps(
                    {
                        "days": days,
                        "total_tasks": len(tasks),
                        "total_images": sum(int(t.total_images or 0) for t in tasks),
                        "total_objects": sum(int(t.total_objects or 0) for t in tasks),
                        "by_day": by_day,
                        "recent_tasks": recent,
                    },
                    ensure_ascii=False,
                )
            finally:
                db.close()

        tools = [
            StructuredTool.from_function(single, name="detect_single_product_image"),
            StructuredTool.from_function(batch, name="detect_product_images"),
            StructuredTool.from_function(zip_images, name="detect_product_zip"),
            StructuredTool.from_function(video, name="detect_product_video"),
            StructuredTool.from_function(list_system_users, name="list_system_users"),
            StructuredTool.from_function(query_detection_stats, name="query_detection_stats"),
        ] + build_interaction_tools("detection")
        llm = ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=settings.DEEPSEEK_TEMPERATURE,
            streaming=True,
            stream_usage=True,
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """你是 VisionPay 零售商品识别 Agent。你的任务是理解用户意图，必要时调用 YOLO 商品检测工具，并用简洁中文总结结果。

规则：
1. 用户消息中的“附件路径”是已上传到服务器的可信附件；单图调用单图工具，多图调用批量工具，ZIP 调用 ZIP 工具，视频调用视频工具。
2. 有附件且用户表达检测、识别、盘点或结算意图时，直接调用工具，不要再次索要路径。
3. 不编造商品、数量、价格或置信度。价格数据尚未接入时，明确说明只能生成识别清单，不能计算金额。
4. 工具完成后先给出图片数或关键帧数和检测总数，再按类别汇总；视频结果说明统计未经跨帧去重，低置信度结果提示人工复核。
5. 管理员询问系统用户、管理员或账号列表时调用用户查询工具；普通用户无权查看全站用户目录。
6. 没有附件时，可以回答本平台识别流程、模型能力和操作问题；不要声称已经执行检测。
7. 始终禁止使用 emoji、颜文字或装饰性图标，除非用户自定义响应指令明确要求使用。未设置自定义指令时，直接给出结论，不要用“好的，我先……”等开场白；字段较多时可使用简洁 Markdown 表格。
8. 若执行检测前确实需要用户选择置信度，调用 request_user_input_form，purpose 固定为 detection.parameters，并把已知阈值放入 known_values；不要自定义表单。图片、ZIP 和视频文件仍通过聊天附件上传。
9. 用户询问检测任务数量、历史或统计（如“今天检测了多少任务”“识别了多少东西”）时，调用 query_detection_stats，按返回数据如实汇总，不要编造数字。
10. 对话历史中带有“[XX Agent 的回复]”前缀的助手消息由对应 Agent 产生，不代表你的身份；你始终是 VisionPay 零售商品识别 Agent。"""
                    + CUSTOM_INSTRUCTIONS_PROMPT,
                ),
                MessagesPlaceholder("chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ]
        )
        agent = create_openai_tools_agent(llm=llm, tools=tools, prompt=prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            # 与 scoped_agent 保持一致，避免多附件/多工具场景被中途掐停。
            max_iterations=10,
            handle_parsing_errors=True,
            verbose=False,
        )

    async def stream(
        self,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None = None,
        custom_instructions: str = "",
    ) -> AsyncGenerator[dict, None]:
        from app.agent.history import build_chat_history

        attachments = "\n".join(f"- {path}" for path in attachment_paths)
        agent_input = message
        if attachments:
            agent_input += f"\n\n本次附件路径：\n{attachments}"

        chat_history = build_chat_history(history)

        detection_emitted = False
        async for event in self.executor.astream_events(
            {
                "input": agent_input,
                "chat_history": chat_history,
                "custom_instructions": render_custom_instructions(custom_instructions),
            },
            version="v2",
        ):
            kind = event.get("event")
            if kind == "on_tool_start":
                yield {
                    "type": "tool_call",
                    "tool": event.get("name", "detection_tool"),
                    "input": event.get("data", {}).get("input", {}),
                }
            elif kind == "on_tool_end":
                tool_name = event.get("name", "detection_tool")
                output = event.get("data", {}).get("output")
                content = _content_text(getattr(output, "content", output))
                if tool_name == "request_user_input_form":
                    yield {
                        "type": "tool_result",
                        "agent": "detection",
                        "tool": tool_name,
                        "content": content,
                    }
                    try:
                        form = json.loads(content)
                    except (TypeError, json.JSONDecodeError):
                        form = None
                    if isinstance(form, dict) and form.get("form_type"):
                        yield {
                            "type": "input_form",
                            "agent": "detection",
                            "form": form,
                        }
                if self.last_detection_result and not detection_emitted:
                    detection_emitted = True
                    yield {"type": "detection_result", "result": self.last_detection_result}
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                usage = usage_metadata(chunk)
                if usage:
                    yield {
                        "type": "model_usage",
                        "agent": "detection",
                        "run_id": str(event.get("run_id") or ""),
                        "usage": usage,
                    }
                content = _content_text(getattr(chunk, "content", ""))
                if content:
                    yield {"type": "text_chunk", "content": content}

        # Some compatible providers do not emit all nested v2 tool events.
        if self.last_detection_result and not detection_emitted:
            yield {"type": "detection_result", "result": self.last_detection_result}
