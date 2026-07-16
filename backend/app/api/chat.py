"""Conversation persistence and SSE endpoints for the VisionPay detection agent."""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent.orchestrator import MultiAgentOrchestrator
from app.agent.detection_agent import DetectionAgent
from app.agent.routing import AGENT_NAMES, RouteDecision
from app.agent.tools.interaction_tools import validate_form_submission
from app.api.auth import get_current_user
from app.api.detection import save_upload
from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import get_db
from app.entity.db_models import AgentHandoff, ChatMessage, ChatSession

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["检测对话"])


def _session_or_404(db, user_id: int, session_uuid: str) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(
            ChatSession.session_uuid == session_uuid,
            ChatSession.user_id == user_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="对话不存在")
    return session


def _serialize_session(session: ChatSession) -> dict:
    return {
        "session_uuid": session.session_uuid,
        "title": session.title or "新对话",
        "message_count": session.message_count or 0,
        "last_message_at": session.last_message_at,
        "created_at": session.created_at,
    }


def _parse_json(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _touch_session(db, session: ChatSession, first_message: str | None = None) -> None:
    session.message_count = (
        db.query(ChatMessage).filter(ChatMessage.session_id == session.id).count()
    )
    session.last_message_at = datetime.now()
    if first_message and (not session.title or session.title == "新对话"):
        session.title = first_message.strip().replace("\n", " ")[:40] or "新对话"
    db.add(session)


@router.get("/status", summary="Agent 配置状态")
async def agent_status(current_user=Depends(get_current_user)):
    configured = bool(
        settings.DEEPSEEK_API_KEY
        and not settings.DEEPSEEK_API_KEY.startswith("sk-your-")
    )
    return {
        "configured": configured,
        "provider": "DeepSeek",
        "model": settings.DEEPSEEK_MODEL,
        "multi_agent": True,
        "agents": ["detection", "dataset", "training", "catalog", "knowledge"],
        "embedding": {
            "configured": bool(settings.DASHSCOPE_API_KEY),
            "provider": "DashScope",
            "model": settings.EMBEDDING_MODEL,
            "dimensions": settings.EMBEDDING_DIMENSIONS,
            "vector_store": "Chroma",
        },
    }


@router.post("/sessions", summary="创建检测对话")
async def create_session(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    body = await request.json()
    title = str(body.get("title") or "新对话").strip()[:200]
    session = ChatSession(
        user_id=current_user.id,
        session_uuid=uuid4().hex,
        title=title or "新对话",
        status="active",
        message_count=0,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _serialize_session(session)


@router.get("/sessions", summary="检测对话历史")
async def list_sessions(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == current_user.id,
            ChatSession.status == "active",
            ChatSession.message_count > 0,
        )
        .order_by(ChatSession.last_message_at.desc(), ChatSession.created_at.desc())
        .all()
    )
    return {"items": [_serialize_session(session) for session in sessions]}


@router.get("/sessions/{session_uuid}", summary="读取检测对话")
async def get_session(
    session_uuid: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user_id = int(current_user.id)
    session = _session_or_404(db, current_user_id, session_uuid)
    messages = []
    for message in session.messages:
        metadata = message.tool_calls if isinstance(message.tool_calls, dict) else {}
        messages.append(
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "agent": message.agent_used,
                "files": metadata.get("attachments", []),
                "tool": metadata.get("tool"),
                "handoff": metadata.get("handoff"),
                "input_form": metadata.get("input_form"),
                "confirmation": metadata.get("confirmation"),
                "result": _parse_json(message.tool_result),
                "created_at": message.created_at,
            }
        )
    return {"session": _serialize_session(session), "messages": messages}


@router.delete("/sessions/{session_uuid}", summary="删除检测对话")
async def delete_session(
    session_uuid: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _session_or_404(db, current_user.id, session_uuid)
    db.delete(session)
    db.commit()
    return {"message": "对话已删除"}


@router.post("/sessions/{session_uuid}/exchanges", summary="保存快捷检测对话")
async def save_exchange(
    session_uuid: str,
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    body = await request.json()
    user_content = str(body.get("user_content") or "").strip()
    assistant_content = str(body.get("assistant_content") or "").strip()
    if not user_content or not assistant_content:
        raise HTTPException(status_code=400, detail="对话内容不能为空")
    attachments = body.get("files") or []
    result = body.get("result")
    session = _session_or_404(db, current_user.id, session_uuid)
    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=user_content,
            agent_used="detection",
            tool_calls={"attachments": attachments},
        )
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=assistant_content,
            agent_used="detection",
            tool_calls={"tool": "yolo_direct"},
            tool_result=json.dumps(result, ensure_ascii=False) if result else None,
        )
    )
    db.flush()
    _touch_session(db, session, user_content)
    db.commit()
    return _serialize_session(session)


@router.post("/upload", summary="上传检测对话附件")
async def upload_attachments(
    files: list[UploadFile] = File(...),
    current_user=Depends(get_current_user),
):
    if len(files) > settings.DETECTION_MAX_BATCH_SIZE:
        raise HTTPException(status_code=400, detail="附件数量超过限制")
    saved = []
    for file in files:
        path = await save_upload(file, allow_zip=True, allow_video=True)
        saved.append({"name": file.filename, "path": str(path)})
    return {"files": saved}


@router.post("/stream", summary="DeepSeek Agent SSE 检测对话")
async def chat_stream(
    request: Request,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    body = await request.json()
    message = str(body.get("message", "")).strip()
    attachment_paths = body.get("attachment_paths") or []
    attachment_names = body.get("attachment_names") or []
    raw_form_submission = body.get("form_submission")
    scene_id = body.get("scene_id")
    session_uuid = str(body.get("session_uuid") or "")
    if not message:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    if not isinstance(attachment_paths, list) or not all(
        isinstance(path, str) for path in attachment_paths
    ):
        raise HTTPException(status_code=400, detail="附件路径格式无效")

    current_user_id = int(current_user.id)
    session = _session_or_404(db, current_user_id, session_uuid)
    form_submission = None
    form_definition = None
    if raw_form_submission is not None:
        if not isinstance(raw_form_submission, dict):
            raise HTTPException(status_code=400, detail="表单提交格式无效")
        form_id = str(raw_form_submission.get("form_id") or "").strip()
        if not form_id or len(form_id) > 64:
            raise HTTPException(status_code=400, detail="表单 ID 无效")
        source_message = next(
            (
                item
                for item in reversed(session.messages)
                if item.role == "assistant"
                and isinstance(item.tool_calls, dict)
                and isinstance(item.tool_calls.get("input_form"), dict)
                and item.tool_calls["input_form"].get("form_id") == form_id
            ),
            None,
        )
        if source_message is None:
            raise HTTPException(status_code=400, detail="表单不存在或不属于当前会话")
        if any(
            item.role == "user"
            and isinstance(item.tool_calls, dict)
            and isinstance(item.tool_calls.get("form_submission"), dict)
            and item.tool_calls["form_submission"].get("form_id") == form_id
            for item in session.messages
        ):
            raise HTTPException(status_code=409, detail="该表单已经提交，请勿重复操作")
        form_definition = source_message.tool_calls["input_form"]
        form_agent = str(form_definition.get("agent") or source_message.agent_used or "")
        if form_agent not in AGENT_NAMES:
            raise HTTPException(status_code=400, detail="表单所属 Agent 无效")
        try:
            normalized_values = validate_form_submission(
                form_definition, raw_form_submission.get("values") or {}
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        form_submission = {
            "form_id": form_id,
            "agent": form_agent,
            "purpose": form_definition.get("purpose"),
            "values": normalized_values,
        }
    last_agent = next(
        (
            item.agent_used
            for item in reversed(session.messages)
            if item.role == "assistant" and item.agent_used
        ),
        None,
    )
    active_dataset_handoff = (
        db.query(AgentHandoff)
        .filter(
            AgentHandoff.user_id == current_user_id,
            AgentHandoff.session_uuid == session_uuid,
            AgentHandoff.domain == "dataset",
            AgentHandoff.status.in_(
                [
                    "ready_for_handoff",
                    "selecting_files",
                    "annotating",
                    "submitting",
                    "failed",
                ]
            ),
            AgentHandoff.expires_at > datetime.now(),
        )
        .order_by(AgentHandoff.created_at.desc())
        .first()
    )
    history = []
    for item in session.messages:
        if item.role not in {"user", "assistant"}:
            continue
        content = item.content
        # 把历史附件路径也拼进上下文，否则 LLM 在多轮对话中看不到之前的附件
        if item.role == "user" and item.tool_calls:
            historical_paths = item.tool_calls.get("attachment_paths") or []
            if historical_paths:
                content += "\n\n本次附件路径：\n" + "\n".join(
                    f"- {p}" for p in historical_paths
                )
            historical_form = item.tool_calls.get("form_submission")
            if isinstance(historical_form, dict):
                content += "\n\n结构化表单参数：\n" + json.dumps(
                    historical_form, ensure_ascii=False
                )
        history.append({"role": item.role, "content": content})
    history = history[-20:]
    if not settings.DEEPSEEK_API_KEY or settings.DEEPSEEK_API_KEY.startswith("sk-your-"):
        raise HTTPException(status_code=503, detail="DeepSeek 尚未配置")
    orchestrator = MultiAgentOrchestrator(
        user_id=current_user_id,
        scene_id=scene_id,
        session_uuid=session_uuid,
        detection_agent_factory=DetectionAgent,
    )
    agent_message = message
    if form_submission and form_definition:
        agent_message += "\n\n[系统校验通过的结构化表单提交]\n" + json.dumps(
            {
                "purpose": form_submission["purpose"],
                "known_values": form_definition.get("known_values") or {},
                "values": form_submission["values"],
            },
            ensure_ascii=False,
        )
        decision = RouteDecision(
            form_submission["agent"],
            "form_submission",
            1.0,
            "继续处理当前会话中已校验的结构化表单",
        )
    else:
        decision = orchestrator.route(
            message,
            has_attachments=bool(attachment_paths),
            preferred_agent=last_agent,
            active_workflow_agent="dataset" if active_dataset_handoff else None,
        )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=message,
            agent_used=decision.agent,
            tool_calls={
                "attachments": attachment_names,
                "attachment_paths": attachment_paths,
                **({"form_submission": form_submission} if form_submission else {}),
            },
        )
    )
    db.flush()
    _touch_session(db, session, message)
    db.commit()

    async def events():
        assistant_content = ""
        result = None
        tool_name = None
        handoff = None
        input_form = None
        confirmation = None
        error_text = None
        yield f"data: {json.dumps({'type': 'session', 'session_uuid': session_uuid})}\n\n"
        try:
            async for event in orchestrator.stream(
                agent_message,
                attachment_paths,
                history,
                decision=decision,
            ):
                if event.get("type") == "text_chunk":
                    assistant_content += event.get("content", "")
                elif event.get("type") == "detection_result":
                    result = event.get("result")
                elif event.get("type") == "tool_call":
                    tool_name = event.get("tool")
                elif event.get("type") == "handoff_required":
                    handoff = {
                        "handoff_id": event.get("handoff_id"),
                        "page_url": event.get("page_url"),
                        "status": event.get("status"),
                        "context": event.get("context") or {},
                    }
                elif event.get("type") == "input_form":
                    input_form = event.get("form") or None
                elif event.get("type") == "confirmation_required":
                    raw_operation = event.get("operation") or {}
                    confirmation = {
                        key: value
                        for key, value in raw_operation.items()
                        if key != "confirmation_token"
                    }
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error("DeepSeek Agent 流式请求失败: %s", exc, exc_info=True)
            error_text = f"Agent 处理失败: {exc}"
            yield f"data: {json.dumps({'type': 'error', 'content': error_text}, ensure_ascii=False)}\n\n"
        finally:
            final_content = (
                assistant_content.strip()
                or error_text
                or ("请填写上方表单后继续。" if input_form else "本次响应已停止。")
            )
            try:
                persist_session = _session_or_404(db, current_user_id, session_uuid)
                db.add(
                    ChatMessage(
                        session_id=persist_session.id,
                        role="assistant",
                        content=final_content,
                        agent_used=decision.agent,
                        tool_calls=(
                            {
                                **({"tool": tool_name} if tool_name else {}),
                                **({"handoff": handoff} if handoff else {}),
                                **({"input_form": input_form} if input_form else {}),
                                **({"confirmation": confirmation} if confirmation else {}),
                            }
                            or None
                        ),
                        tool_result=(
                            json.dumps(result, ensure_ascii=False) if result else None
                        ),
                    )
                )
                db.flush()
                _touch_session(db, persist_session)
                db.commit()
            except Exception:
                db.rollback()
                logger.error("检测对话持久化失败", exc_info=True)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
