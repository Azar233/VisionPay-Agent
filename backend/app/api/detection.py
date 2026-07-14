"""Direct detection APIs used by the low-latency workbench controls."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.api.camera import configured_ip_webcam_url
from app.config.settings import settings
from app.database.session import get_db
from app.entity.db_models import DetectionTask
from app.services.detection_service import DetectionServiceError, detection_service
from app.storage.video_task_store import video_task_store

router = APIRouter(prefix="/api/detection", tags=["商品检测"])
_CAMERA_SESSION_LOCK = threading.Lock()


def _upload_root() -> Path:
    root = Path(settings.DETECTION_UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(filename: str | None) -> str:
    original = Path(filename or "upload").name
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", original)
    return f"{uuid4().hex}_{clean}"


async def save_upload(
    file: UploadFile,
    *,
    allow_zip: bool = False,
    allow_video: bool = False,
    video_only: bool = False,
) -> Path:
    suffix = Path(file.filename or "").suffix.lower()
    video_suffixes = {".mp4", ".avi", ".mov", ".mkv"}
    allowed = set() if video_only else {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    if allow_zip:
        allowed.add(".zip")
    if allow_video:
        allowed.update(video_suffixes)
    if suffix not in allowed:
        if video_only:
            detail = "仅支持 MP4、AVI、MOV 或 MKV 视频"
        else:
            detail = "仅支持已启用的图片、ZIP 或视频格式" if allow_video else "仅支持常见图片格式或 ZIP 文件"
        raise HTTPException(status_code=415, detail=detail)

    limit_mb = settings.DETECTION_VIDEO_MAX_FILE_MB if suffix in video_suffixes else settings.DETECTION_MAX_FILE_MB
    limit = limit_mb * 1024 * 1024
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"单个文件不能超过 {limit_mb} MB",
        )
    path = _upload_root() / _safe_name(file.filename)
    path.write_bytes(content)
    return path


def _detection_kwargs(user_id: int, scene_id: int | None, conf: float, iou: float):
    return {"user_id": user_id, "scene_id": scene_id, "conf": conf, "iou": iou}


@router.post("/single", summary="单张商品图片检测")
async def detect_single(
    file: UploadFile = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    current_user=Depends(get_current_user),
):
    path = await save_upload(file)
    try:
        return await run_in_threadpool(
            detection_service.detect_single,
            path,
            **_detection_kwargs(current_user.id, scene_id, conf, iou),
        )
    except DetectionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batch", summary="批量商品图片检测")
async def detect_batch(
    files: list[UploadFile] = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    current_user=Depends(get_current_user),
):
    if len(files) > settings.DETECTION_MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"单次最多上传 {settings.DETECTION_MAX_BATCH_SIZE} 张图片",
        )
    paths = [await save_upload(file) for file in files]
    try:
        return await run_in_threadpool(
            detection_service.detect_batch,
            paths,
            **_detection_kwargs(current_user.id, scene_id, conf, iou),
        )
    except DetectionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/zip", summary="ZIP 商品图片批量检测")
async def detect_zip(
    file: UploadFile = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    current_user=Depends(get_current_user),
):
    path = await save_upload(file, allow_zip=True)
    if path.suffix.lower() != ".zip":
        raise HTTPException(status_code=415, detail="该接口只接受 ZIP 文件")
    try:
        return await run_in_threadpool(
            detection_service.detect_zip,
            path,
            **_detection_kwargs(current_user.id, scene_id, conf, iou),
        )
    except DetectionServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _video_result_path(task_id: int) -> Path:
    root = Path(settings.VIDEO_RESULT_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"task_{task_id}.json"


def _write_video_result(task_id: int, result: dict) -> Path:
    path = _video_result_path(task_id)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def _run_video_detection(
    *,
    task_id: int,
    path: Path,
    user_id: int,
    scene_id: int,
    conf: float,
    iou: float,
    frame_sample_rate: int,
    max_frames: int,
) -> None:
    def update(progress: int, message: str) -> None:
        video_task_store.set(
            task_id,
            {"status": "processing", "progress": progress, "message": message},
        )

    try:
        result = detection_service.detect_video(
            path,
            task_id=task_id,
            user_id=user_id,
            scene_id=scene_id,
            conf=conf,
            iou=iou,
            frame_sample_rate=frame_sample_rate,
            max_frames=max_frames,
            progress_callback=update,
        )
        result_path = _write_video_result(task_id, result)
        video_task_store.set(
            task_id,
            {
                "status": "completed",
                "progress": 100,
                "message": "视频检测完成",
                "result_path": str(result_path),
            },
        )
    except Exception as exc:
        video_task_store.set(
            task_id,
            {"status": "failed", "progress": 0, "message": str(exc)},
        )
    finally:
        path.unlink(missing_ok=True)


@router.post("/video", summary="上传视频并创建后台检测任务")
async def detect_video_api(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    scene_id: int | None = Form(None),
    conf: float = Form(0.25, ge=0.05, le=0.95),
    iou: float = Form(0.45, ge=0.05, le=0.95),
    frame_sample_rate: int = Form(settings.VIDEO_FRAME_SAMPLE_RATE, ge=1, le=300),
    max_frames: int = Form(
        settings.VIDEO_MAX_KEY_FRAMES,
        ge=1,
        le=settings.VIDEO_MAX_KEY_FRAMES,
    ),
    current_user=Depends(get_current_user),
):
    path = await save_upload(file, allow_video=True, video_only=True)
    try:
        task_info = await run_in_threadpool(
            detection_service.create_video_task,
            user_id=current_user.id,
            scene_id=scene_id,
            conf=conf,
            iou=iou,
        )
    except DetectionServiceError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task_id = task_info["task_id"]
    video_task_store.set(
        task_id,
        {"status": "pending", "progress": 0, "message": "视频已上传，等待处理"},
    )
    background_tasks.add_task(
        _run_video_detection,
        task_id=task_id,
        path=path,
        user_id=current_user.id,
        scene_id=task_info["scene_id"],
        conf=conf,
        iou=iou,
        frame_sample_rate=frame_sample_rate,
        max_frames=max_frames,
    )
    return {
        "task_id": task_id,
        "status": "pending",
        "message": "视频已上传，正在后台处理",
        "filename": file.filename,
    }


@router.get("/video/status/{task_id}", summary="查询视频检测进度和结果")
async def get_video_detection_status(
    task_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
    if not task or task.user_id != current_user.id or task.task_type != "video":
        raise HTTPException(status_code=404, detail="视频检测任务不存在")
    progress = video_task_store.get(task_id) or {
        "status": task.status,
        "progress": 100 if task.status == "completed" else 0,
        "message": task.error_message or "任务状态已从数据库恢复",
    }
    response = {"task_id": task_id, **progress}
    if response["status"] == "completed":
        result_path_value = response.pop("result_path", None)
        result_path = Path(result_path_value) if result_path_value else _video_result_path(task_id)
        if result_path.is_file():
            response["result"] = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            response.update(
                {"status": "failed", "message": "视频结果文件已过期或不存在"}
            )
    return response


def _camera_options(payload: dict) -> dict:
    """Validate the initial config message accepted by the camera socket."""
    mode = str(payload.get("mode", "cpu")).lower()
    if mode != "cpu":
        raise ValueError("当前 PyTorch 环境未启用 CUDA，实时检测仅支持 cpu 模式")
    conf = float(payload.get("conf", settings.CAMERA_CONFIDENCE))
    iou = float(payload.get("iou", settings.CAMERA_IOU))
    if not 0.05 <= conf <= 0.95 or not 0.05 <= iou <= 0.95:
        raise ValueError("conf 和 iou 必须在 0.05 到 0.95 之间")
    scene_id = payload.get("scene_id")
    if scene_id is not None:
        scene_id = int(scene_id)
        if scene_id < 1:
            raise ValueError("scene_id 必须为正整数")
    return {"mode": mode, "conf": conf, "iou": iou, "scene_id": scene_id}


async def _camera_control(websocket: WebSocket, stopped: asyncio.Event) -> None:
    """Listen for an explicit close message or a disconnected browser."""
    try:
        while not stopped.is_set():
            message = await websocket.receive_json()
            if message.get("type") == "close":
                stopped.set()
                return
    except (WebSocketDisconnect, RuntimeError):
        stopped.set()


@router.websocket("/camera")
async def camera_detection_ws(websocket: WebSocket):
    """Pull the configured IP Webcam MJPEG stream and return annotated frames."""
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.cors_origins_list:
        await websocket.close(code=1008, reason="不允许的 WebSocket 来源")
        return
    if not _CAMERA_SESSION_LOCK.acquire(blocking=False):
        await websocket.accept()
        await websocket.send_json(
            {"type": "error", "message": "摄像头正在被另一个检测会话使用"}
        )
        await websocket.close(code=1013)
        return

    capture = None
    stopped = asyncio.Event()
    control_task = None
    await websocket.accept()
    try:
        initial = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if initial.get("type") != "config":
            raise ValueError("连接后必须先发送 config 消息")
        options = _camera_options(initial)
        stream_url = configured_ip_webcam_url()

        def open_capture():
            import cv2

            cap = cv2.VideoCapture(stream_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                cap.release()
                raise DetectionServiceError("无法打开 IP Webcam MJPEG 视频流")
            return cap

        capture = await run_in_threadpool(open_capture)
        model_context = await run_in_threadpool(
            detection_service.prepare_realtime_model,
            scene_id=options["scene_id"],
            image_size=settings.CAMERA_IMAGE_SIZE,
            conf=options["conf"],
            iou=options["iou"],
        )
        await websocket.send_json(
            {
                "type": "config_ok",
                "mode": "cpu",
                "target_fps": settings.CAMERA_TARGET_FPS,
                "image_size": settings.CAMERA_IMAGE_SIZE,
                "model": model_context["model_name"],
                "scene": model_context["scene"],
                "source": "IP Webcam",
            }
        )
        control_task = asyncio.create_task(_camera_control(websocket, stopped))
        frame_count = 0
        failed_reads = 0
        previous_result_at = time.perf_counter()
        frame_interval = 1 / max(0.5, settings.CAMERA_TARGET_FPS)

        while not stopped.is_set():
            cycle_started = time.perf_counter()
            ok, frame = await run_in_threadpool(capture.read)
            if not ok or frame is None:
                failed_reads += 1
                if failed_reads >= 5:
                    raise DetectionServiceError("IP Webcam 连续读取失败，请检查手机网络")
                await asyncio.sleep(0.1)
                continue
            failed_reads = 0
            result = await run_in_threadpool(
                detection_service.detect_realtime_frame,
                model_context["model"],
                frame,
                conf=options["conf"],
                iou=options["iou"],
                image_size=settings.CAMERA_IMAGE_SIZE,
                jpeg_quality=settings.CAMERA_JPEG_QUALITY,
            )
            frame_count += 1
            now = time.perf_counter()
            result.update(
                {
                    "type": "result",
                    "frame_count": frame_count,
                    "fps": round(1 / max(now - previous_result_at, 0.001), 1),
                }
            )
            previous_result_at = now
            await websocket.send_json(result)
            remaining = frame_interval - (time.perf_counter() - cycle_started)
            if remaining > 0:
                try:
                    await asyncio.wait_for(stopped.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass
    except asyncio.TimeoutError:
        await websocket.send_json({"type": "error", "message": "等待摄像头配置超时"})
    except WebSocketDisconnect:
        pass
    except (ValueError, DetectionServiceError) as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except RuntimeError:
            pass
    except Exception as exc:
        try:
            await websocket.send_json(
                {"type": "error", "message": f"实时检测异常: {exc}"}
            )
        except RuntimeError:
            pass
    finally:
        stopped.set()
        if control_task:
            control_task.cancel()
            try:
                await control_task
            except asyncio.CancelledError:
                pass
        if capture is not None:
            await run_in_threadpool(capture.release)
        try:
            await websocket.close()
        except RuntimeError:
            pass
        _CAMERA_SESSION_LOCK.release()
