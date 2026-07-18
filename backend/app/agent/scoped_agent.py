"""Reusable DeepSeek tool-calling executor for a single management domain."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from app.agent.detection_agent import AgentConfigurationError
from app.agent.custom_instructions import (
    CUSTOM_INSTRUCTIONS_PROMPT,
    render_custom_instructions,
)
from app.agent.usage import usage_metadata
from app.config.settings import settings


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


class ScopedToolAgent:
    def __init__(self, *, name: str, system_prompt: str, tools: list) -> None:
        if not settings.DEEPSEEK_API_KEY or settings.DEEPSEEK_API_KEY.startswith("sk-your-"):
            raise AgentConfigurationError("DeepSeek 尚未配置")
        self.name = name
        self.tools = tools
        self.executor = self._build_executor(system_prompt)

    def _build_executor(self, system_prompt: str):
        from langchain.agents import AgentExecutor, create_openai_tools_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        from langchain_openai import ChatOpenAI

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
                    system_prompt
                    + "\n\n本轮相关长期记忆：\n{runtime_context}"
                    + CUSTOM_INSTRUCTIONS_PROMPT,
                ),
                MessagesPlaceholder("chat_history", optional=True),
                ("human", "{input}"),
                MessagesPlaceholder("agent_scratchpad"),
            ]
        )
        agent = create_openai_tools_agent(llm=llm, tools=self.tools, prompt=prompt)
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            # 批量操作（如一次为 6 个商品生成改价预览）需要 查询+N个预览+回复 共 N+2 步，
            # 上限过低会被中途掐停且前端拿不到任何输出。
            max_iterations=10,
            handle_parsing_errors=True,
            verbose=False,
        )

    async def stream(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        runtime_context: str = "无",
        custom_instructions: str = "",
    ) -> AsyncGenerator[dict, None]:
        from app.agent.history import build_chat_history

        chat_history = build_chat_history(history)

        async for event in self.executor.astream_events(
            {
                "input": message,
                "chat_history": chat_history,
                "runtime_context": runtime_context,
                "custom_instructions": render_custom_instructions(custom_instructions),
            },
            version="v2",
        ):
            kind = event.get("event")
            if kind == "on_tool_start":
                yield {
                    "type": "tool_call",
                    "agent": self.name,
                    "tool": event.get("name", "tool"),
                    "input": event.get("data", {}).get("input", {}),
                }
            elif kind == "on_tool_end":
                output = event.get("data", {}).get("output")
                tool_name = event.get("name", "tool")
                content = _content_text(getattr(output, "content", output))
                yield {
                    "type": "tool_result",
                    "agent": self.name,
                    "tool": tool_name,
                    "content": content,
                }
                if tool_name == "prepare_add_samples_handoff":
                    try:
                        handoff = json.loads(content)
                    except (TypeError, json.JSONDecodeError):
                        handoff = None
                    if isinstance(handoff, dict) and handoff.get("handoff_uuid"):
                        yield {
                            "type": "handoff_required",
                            "agent": self.name,
                            "handoff_id": handoff["handoff_uuid"],
                            "page_url": handoff.get("page_url"),
                            "status": handoff.get("status"),
                            "context": handoff.get("context") or {},
                        }
                if tool_name == "request_user_input_form":
                    try:
                        form = json.loads(content)
                    except (TypeError, json.JSONDecodeError):
                        form = None
                    if isinstance(form, dict) and form.get("form_type"):
                        yield {
                            "type": "input_form",
                            "agent": self.name,
                            "form": form,
                        }
                if tool_name.startswith("preview_"):
                    try:
                        operation = json.loads(content)
                    except (TypeError, json.JSONDecodeError):
                        operation = None
                    if isinstance(operation, dict) and operation.get("operation_uuid"):
                        yield {
                            "type": "confirmation_required",
                            "agent": self.name,
                            "operation": operation,
                        }
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                usage = usage_metadata(chunk)
                if usage:
                    yield {
                        "type": "model_usage",
                        "agent": self.name,
                        "run_id": str(event.get("run_id") or ""),
                        "usage": usage,
                    }
                content = _content_text(getattr(chunk, "content", ""))
                if content:
                    yield {"type": "text_chunk", "agent": self.name, "content": content}
