"""DeepSeek-powered retail detection agent with request-scoped tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncGenerator

from app.config.settings import settings
from app.core.logger import get_logger
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

        tools = [
            StructuredTool.from_function(single, name="detect_single_product_image"),
            StructuredTool.from_function(batch, name="detect_product_images"),
            StructuredTool.from_function(zip_images, name="detect_product_zip"),
            StructuredTool.from_function(video, name="detect_product_video"),
        ]
        llm = ChatOpenAI(
            model=settings.DEEPSEEK_MODEL,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=settings.DEEPSEEK_TEMPERATURE,
            streaming=True,
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
5. 没有附件时，可以回答本平台识别流程、模型能力和操作问题；不要声称已经执行检测。""",
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
            max_iterations=4,
            handle_parsing_errors=True,
            verbose=False,
        )

    async def stream(
        self,
        message: str,
        attachment_paths: list[str],
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[dict, None]:
        from langchain_core.messages import AIMessage, HumanMessage

        attachments = "\n".join(f"- {path}" for path in attachment_paths)
        agent_input = message
        if attachments:
            agent_input += f"\n\n本次附件路径：\n{attachments}"

        chat_history = []
        for item in history or []:
            if item.get("role") == "user":
                chat_history.append(HumanMessage(content=item.get("content", "")))
            elif item.get("role") == "assistant":
                chat_history.append(AIMessage(content=item.get("content", "")))

        detection_emitted = False
        async for event in self.executor.astream_events(
            {"input": agent_input, "chat_history": chat_history}, version="v2"
        ):
            kind = event.get("event")
            if kind == "on_tool_start":
                yield {
                    "type": "tool_call",
                    "tool": event.get("name", "detection_tool"),
                    "input": event.get("data", {}).get("input", {}),
                }
            elif kind == "on_tool_end":
                if self.last_detection_result and not detection_emitted:
                    detection_emitted = True
                    yield {"type": "detection_result", "result": self.last_detection_result}
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                content = _content_text(getattr(chunk, "content", ""))
                if content:
                    yield {"type": "text_chunk", "content": content}

        # Some compatible providers do not emit all nested v2 tool events.
        if self.last_detection_result and not detection_emitted:
            yield {"type": "detection_result", "result": self.last_detection_result}
