"""Token-aware chat history and persistent task state for Agent conversations."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.entity.db_models import (
    AgentHandoff,
    AgentPendingOperation,
    ChatMessage,
    ChatSession,
)


AGENTS = {"detection", "dataset", "training", "catalog", "knowledge"}
PENDING_WORKFLOW_STATUSES = {
    "active",
    "awaiting_input",
    "awaiting_confirmation",
    "awaiting_handoff",
    "ready_for_handoff",
    "selecting_files",
    "annotating",
    "submitting",
    "failed",
}
SENSITIVE_KEYS = {
    "confirmation_token",
    "confirmation_token_hash",
    "token",
    "api_key",
    "password",
    "attachment_paths",
    "model_path",
    "file_path",
}
ENTITY_KEYS = {
    "dataset_id",
    "dataset_version_id",
    "product_id",
    "existing_product_id",
    "model_version_id",
    "task_id",
    "scene_id",
    "handoff_id",
    "handoff_uuid",
    "operation_uuid",
    "version",
    "dataset_version",
    "product_name",
    "model_name",
    "class_name",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class ConversationContextService:
    SCHEMA_VERSION = 1

    def __init__(self) -> None:
        self._encoding = None

    def _encoder(self):
        if self._encoding is None:
            try:
                import tiktoken

                self._encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:  # pragma: no cover - dependency/runtime fallback
                self._encoding = False
        return self._encoding

    def token_count(self, text: str) -> int:
        encoder = self._encoder()
        if encoder:
            return len(encoder.encode(text or ""))
        return max(1, math.ceil(len(text or "") / 4))

    def _trim_tokens(self, text: str, limit: int, *, keep_tail: bool = True) -> str:
        value = str(text or "")
        if limit <= 0 or self.token_count(value) <= limit:
            return value
        encoder = self._encoder()
        if encoder:
            tokens = encoder.encode(value)
            selected = tokens[-limit:] if keep_tail else tokens[:limit]
            return encoder.decode(selected)
        chars = max(1, limit * 4)
        return value[-chars:] if keep_tail else value[:chars]

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "schema_version": ConversationContextService.SCHEMA_VERSION,
            "active_agent": None,
            "active_workflow": None,
            "entities": {},
            "known_values": {},
            "missing_fields": [],
            "pending": {},
            "last_tool": None,
            "updated_at": None,
        }

    def normalize_state(self, value: Any) -> dict[str, Any]:
        state = self._default_state()
        if isinstance(value, dict):
            for key in state:
                if key in value:
                    state[key] = deepcopy(value[key])
        if state.get("active_agent") not in AGENTS:
            state["active_agent"] = None
        for key in ("entities", "known_values", "pending"):
            if not isinstance(state.get(key), dict):
                state[key] = {}
        if not isinstance(state.get("missing_fields"), list):
            state["missing_fields"] = []
        return state

    def _sanitize(self, value: Any, *, depth: int = 0) -> Any:
        if depth > 4:
            return "[内容已折叠]"
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = str(key).lower()
                if normalized in SENSITIVE_KEYS or normalized.endswith("_token"):
                    continue
                result[str(key)] = self._sanitize(item, depth=depth + 1)
            return result
        if isinstance(value, list):
            items = [self._sanitize(item, depth=depth + 1) for item in value[:8]]
            if len(value) > 8:
                items.append(f"其余 {len(value) - 8} 项已折叠")
            return items
        if isinstance(value, str):
            limit = int(settings.AGENT_CONTEXT_TOOL_RESULT_CHARS)
            return value if len(value) <= limit else value[:limit] + "…"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return str(value)

    def _extract_entities(self, value: Any, target: dict[str, Any]) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key)
                if normalized in ENTITY_KEYS and isinstance(item, (str, int, float)):
                    target[normalized] = item
                self._extract_entities(item, target)
        elif isinstance(value, list):
            for item in value[:20]:
                self._extract_entities(item, target)

    @staticmethod
    def _parse_result(content: str | None) -> Any:
        if not content:
            return None
        try:
            return json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return content

    def reconcile(
        self, db: Session, session: ChatSession, *, user_id: int
    ) -> dict[str, Any]:
        """Refresh pending workflow facts from authoritative database records."""
        state = self.normalize_state(session.context_state)
        pending = dict(state["pending"])

        handoff = (
            db.query(AgentHandoff)
            .filter(
                AgentHandoff.user_id == user_id,
                AgentHandoff.session_uuid == session.session_uuid,
            )
            .order_by(AgentHandoff.updated_at.desc(), AgentHandoff.id.desc())
            .first()
        )
        if (
            handoff
            and handoff.status in PENDING_WORKFLOW_STATUSES
            and handoff.expires_at > datetime.now()
        ):
            state["active_agent"] = handoff.domain if handoff.domain in AGENTS else state["active_agent"]
            state["active_workflow"] = {
                "agent": handoff.domain,
                "purpose": handoff.action,
                "status": handoff.status,
            }
            pending["handoff_id"] = handoff.handoff_uuid
            pending["handoff_status"] = handoff.status
            self._extract_entities(handoff.context or {}, state["entities"])
        else:
            workflow = state.get("active_workflow")
            if (
                handoff
                and isinstance(workflow, dict)
                and workflow.get("agent") == handoff.domain
                and str(workflow.get("purpose") or "").startswith("dataset.")
            ):
                workflow["status"] = (
                    "expired" if handoff.expires_at <= datetime.now() else handoff.status
                )
            pending.pop("handoff_id", None)
            pending.pop("handoff_status", None)

        operation = (
            db.query(AgentPendingOperation)
            .filter(
                AgentPendingOperation.user_id == user_id,
                AgentPendingOperation.session_uuid == session.session_uuid,
            )
            .order_by(AgentPendingOperation.updated_at.desc(), AgentPendingOperation.id.desc())
            .first()
        )
        if (
            operation
            and operation.status in {"pending", "executing"}
            and (
                operation.status == "executing"
                or operation.token_expires_at > datetime.now()
            )
        ):
            state["active_agent"] = operation.domain if operation.domain in AGENTS else state["active_agent"]
            state["active_workflow"] = {
                "agent": operation.domain,
                "purpose": operation.action,
                "status": "awaiting_confirmation" if operation.status == "pending" else operation.status,
            }
            pending["operation_uuid"] = operation.operation_uuid
            pending["operation_status"] = operation.status
            self._extract_entities(operation.parameters or {}, state["entities"])
        else:
            workflow = state.get("active_workflow")
            if (
                operation
                and isinstance(workflow, dict)
                and workflow.get("purpose") == operation.action
            ):
                workflow["status"] = (
                    "expired"
                    if operation.status == "pending"
                    and operation.token_expires_at <= datetime.now()
                    else operation.status
                )
                if operation.result:
                    self._extract_entities(operation.result, state["entities"])
            pending.pop("operation_uuid", None)
            pending.pop("operation_status", None)

        state["pending"] = pending
        session.context_state = state
        return state

    def refresh_session(
        self, db: Session, *, user_id: int, session_uuid: str
    ) -> dict[str, Any] | None:
        session = (
            db.query(ChatSession)
            .filter(
                ChatSession.user_id == user_id,
                ChatSession.session_uuid == session_uuid,
            )
            .first()
        )
        if session is None:
            return None
        state = self.reconcile(db, session, user_id=user_id)
        db.add(session)
        db.commit()
        return state

    def active_workflow_agent(self, state: dict[str, Any]) -> str | None:
        workflow = state.get("active_workflow")
        if not isinstance(workflow, dict):
            return None
        agent = workflow.get("agent")
        status = workflow.get("status")
        if agent in AGENTS and status in PENDING_WORKFLOW_STATUSES:
            return str(agent)
        return None

    def render_state(self, state: dict[str, Any]) -> str:
        safe = self._sanitize(self.normalize_state(state))
        return "系统维护的结构化会话状态（仅作当前任务事实，不代表操作已执行）：\n" + _json(safe)

    def _message_content(self, message: ChatMessage) -> str:
        content = message.content or ""
        metadata = message.tool_calls if isinstance(message.tool_calls, dict) else {}
        if message.role == "user":
            paths = metadata.get("attachment_paths") or []
            if paths:
                content += "\n\n本次附件路径：\n" + "\n".join(f"- {path}" for path in paths)
            submission = metadata.get("form_submission")
            if isinstance(submission, dict):
                content += "\n\n结构化表单参数：\n" + _json(self._sanitize(submission))
        elif message.role == "assistant":
            facts: dict[str, Any] = {}
            tools = metadata.get("tools") or ([metadata["tool"]] if metadata.get("tool") else [])
            if tools:
                facts["tools"] = tools
            for key in ("handoff", "input_form", "confirmation"):
                if isinstance(metadata.get(key), dict):
                    facts[key] = self._sanitize(metadata[key])
            result = self._parse_result(message.tool_result)
            if result is not None:
                facts["tool_result"] = self._sanitize(result)
            if facts:
                content += "\n\n[系统保存的本轮结构化事实]\n" + _json(facts)
        return content

    def _summary_line(self, message: ChatMessage) -> str:
        role = "用户" if message.role == "user" else f"助手/{message.agent_used or 'unknown'}"
        content = " ".join((message.content or "").split())
        content = content[:360] + ("…" if len(content) > 360 else "")
        parts = [f"- {role}: {content}"]
        metadata = message.tool_calls if isinstance(message.tool_calls, dict) else {}
        tools = metadata.get("tools") or ([metadata["tool"]] if metadata.get("tool") else [])
        if tools:
            parts.append("工具=" + ",".join(str(tool) for tool in tools))
        result = self._parse_result(message.tool_result)
        facts: dict[str, Any] = {}
        self._extract_entities(result, facts)
        if facts:
            parts.append("实体=" + _json(facts))
        return "；".join(parts)

    def prepare_history(self, session: ChatSession) -> tuple[list[dict[str, str]], int]:
        """Build summary + recent messages within the configured token budget."""
        messages = [item for item in session.messages if item.role in {"user", "assistant"}]
        recent_count = max(4, int(settings.AGENT_CONTEXT_RECENT_MESSAGES))
        cutoff = max(0, len(messages) - recent_count)
        summarized_id = int(session.summarized_message_id or 0)
        new_summary_lines = [
            self._summary_line(item)
            for item in messages[:cutoff]
            if int(item.id or 0) > summarized_id
        ]
        summary = str(session.context_summary or "").strip()
        if new_summary_lines:
            summary = "\n".join(part for part in [summary, *new_summary_lines] if part)
            session.context_summary = self._trim_tokens(
                summary, int(settings.AGENT_CONTEXT_SUMMARY_TOKENS), keep_tail=True
            ).strip()
            session.summarized_message_id = messages[cutoff - 1].id
            summary = session.context_summary or ""

        budget = max(1000, int(settings.AGENT_CONTEXT_HISTORY_TOKENS))
        system_limit = max(200, budget // 3)
        state = self.normalize_state(session.context_state)
        state_text = self._trim_tokens(
            self.render_state(state), system_limit, keep_tail=False
        )
        system_items = [{"role": "system", "content": state_text}]
        if summary:
            summary_text = self._trim_tokens(summary, system_limit, keep_tail=True)
            system_items.insert(
                0,
                {"role": "system", "content": "较早对话增量摘要：\n" + summary_text},
            )

        used = sum(self.token_count(item["content"]) + 4 for item in system_items)
        recent: list[dict[str, str]] = []
        for message in reversed(messages[cutoff:]):
            content = self._message_content(message)
            cost = self.token_count(content) + 4
            if recent and used + cost > budget:
                break
            if used + cost > budget:
                content = self._trim_tokens(content, max(200, budget - used - 4), keep_tail=True)
                cost = self.token_count(content) + 4
            recent.append({"role": message.role, "content": content})
            used += cost
        recent.reverse()
        return [*system_items, *recent], used

    def apply_turn(
        self,
        session: ChatSession,
        *,
        agent: str,
        form_submission: dict[str, Any] | None = None,
        input_form: dict[str, Any] | None = None,
        handoff: dict[str, Any] | None = None,
        confirmation: dict[str, Any] | None = None,
        tool_events: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        state = self.normalize_state(session.context_state)
        if agent in AGENTS:
            state["active_agent"] = agent

        if form_submission:
            state["known_values"].update(form_submission.get("values") or {})
            state["pending"].pop("form_id", None)
            state["missing_fields"] = []
            state["active_workflow"] = {
                "agent": agent,
                "purpose": form_submission.get("purpose"),
                "status": "active",
            }
            self._extract_entities(form_submission, state["entities"])

        last_tool = None
        for event in tool_events:
            tool_name = str(event.get("tool") or "tool")
            tool_input = event.get("input") if isinstance(event.get("input"), dict) else {}
            result = event.get("result")
            parsed = self._parse_result(result) if isinstance(result, str) else result
            self._extract_entities(tool_input, state["entities"])
            self._extract_entities(parsed, state["entities"])
            state["known_values"].update(
                {key: value for key, value in tool_input.items() if key not in SENSITIVE_KEYS}
            )
            last_tool = {
                "name": tool_name,
                "agent": agent,
                "input": self._sanitize(tool_input),
                "result": self._sanitize(parsed),
            }
        if last_tool:
            state["last_tool"] = last_tool

        if input_form:
            known = input_form.get("known_values") or {}
            state["known_values"].update(known)
            missing = []
            for field in input_form.get("fields") or []:
                name = field.get("name")
                if field.get("required", True) and name and name not in known:
                    missing.append(name)
            state["missing_fields"] = missing
            state["pending"]["form_id"] = input_form.get("form_id")
            state["active_workflow"] = {
                "agent": agent,
                "purpose": input_form.get("purpose"),
                "status": "awaiting_input",
            }
            self._extract_entities(input_form, state["entities"])

        if handoff:
            state["pending"]["handoff_id"] = handoff.get("handoff_id")
            state["pending"]["handoff_status"] = handoff.get("status")
            state["active_workflow"] = {
                "agent": agent,
                "purpose": "dataset.add_samples" if agent == "dataset" else None,
                "status": handoff.get("status") or "awaiting_handoff",
            }
            self._extract_entities(handoff, state["entities"])

        if confirmation:
            state["pending"]["operation_uuid"] = confirmation.get("operation_uuid")
            state["pending"]["operation_status"] = confirmation.get("status") or "pending"
            state["active_workflow"] = {
                "agent": agent,
                "purpose": confirmation.get("action"),
                "status": "awaiting_confirmation",
            }
            self._extract_entities(confirmation, state["entities"])

        state["updated_at"] = datetime.now().isoformat()
        session.context_state = state
        return state


conversation_context_service = ConversationContextService()
