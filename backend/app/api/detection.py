"""Direct detection APIs used by the low-latency workbench controls."""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from pathlib import Path
from uuid import uuid4

import torch
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
from app.api.camera import configured_ip_webcam_url, normalize_ip_webcam_url
from app.config.settings import settings
from app.database.session import get_db
from app.entity.db_models import DetectionTask
from app.services.detection_service import DetectionServiceError, detection_service
from app.services.realtime_stabilizer import RealtimeDetectionStabilizer
from app.storage.video_task_store import video_task_store

router = APIRouter(prefix="/api/detection", tags=["商品检测"])
_CAMERA_SESSION_CLAIM_LOCK = asyncio.Lock()
_CAMERA_ACTIVE_SESSION: dict | None = None
CAMERA_REPLACED_CLOSE_CODE = 4001


class _LatestCameraFrame:
    """Continuously drain a capture and expose only its newest frame."""

    def __init__(self, capture) -> None:
        self.capture = capture
        self._condition = threading.Condition()
        self._stopped = threading.Event()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="ip-webcam-latest-frame",
            daemon=True,
        )
        self._sequence = 0
        self._frame = None
        self._captured_at = 0.0
        self._error: str | None = None
        self._consecutive_failures = 0

    def start(self) -> None:
        self._thread.start()

    def _read_loop(self) -> None:
        while not self._stopped.is_set():
            ok, frame = self.capture.read()
            captured_at = time.perf_counter()
            with self._condition:
                if self._stopped.is_set():
                    break
                if ok and frame is not None:
                    self._sequence += 1
                    self._frame = frame
                    self._captured_at = captured_at
                    self._consecutive_failures = 0
                else:
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= 8:
                        self._error = "IP Webcam 连续读取失败，请检查手机网络"
                        self._stopped.set()
                self._condition.notify_all()
            # Real MJPEG reads block at the source frame rate. The tiny yield
            # also prevents a broken/virtual capture from spinning at 100% CPU.
            time.sleep(0.001 if ok else 0.05)
        # 线程退出前自行释放 capture，避免主线程和读线程竞争 FFmpeg 资源
        try:
            self.capture.release()
        except Exception:
            pass

    def latest(self, after_sequence: int, timeout: float = 1.0):
        with self._condition:
            self._condition.wait_for(
                lambda: (
                    self._sequence > after_sequence
                    or self._error is not None
                    or self._stopped.is_set()
                ),
                timeout=timeout,
            )
            if self._error:
                raise DetectionServiceError(self._error)
            if self._sequence <= after_sequence or self._frame is None:
                return None
            return self._sequence, self._frame, self._captured_at

    def stop(self) -> None:
        self._stopped.set()
        with self._condition:
            self._condition.notify_all()
        # 先等读线程完全退出（它会自己释放 capture），再给 5 秒超时
        if self._thread.is_alive():
            self._thread.join(timeout=5)


def _open_camera_capture(stream_url: str):
    """Open an FFmpeg-backed MJPEG capture with bounded network waits."""
    import cv2

    capture = None
    params = []
    if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
        params.extend([cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000])
    if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
        params.extend(
            [cv2.CAP_PROP_READ_TIMEOUT_MSEC, settings.CAMERA_READ_TIMEOUT_MS]
        )
    if params and hasattr(cv2, "CAP_FFMPEG"):
        try:
            capture = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG, params)
        except (TypeError, cv2.error):
            capture = None
    if capture is None or not capture.isOpened():
        if capture is not None:
            capture.release()
        capture = cv2.VideoCapture(stream_url)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not capture.isOpened():
        capture.release()
        raise DetectionServiceError("无法打开 IP Webcam MJPEG 视频流")
    return capture


async def _claim_camera_session() -> dict:
    """Claim the camera, replacing a stale/older browser session if needed."""
    global _CAMERA_ACTIVE_SESSION

    session = {
        "id": uuid4().hex,
        "stopped": asyncio.Event(),
        "closed": asyncio.Event(),
        "replaced": False,
    }
    async with _CAMERA_SESSION_CLAIM_LOCK:
        previous = _CAMERA_ACTIVE_SESSION
        if previous is not None:
            previous["replaced"] = True
            previous["stopped"].set()
            try:
                await asyncio.wait_for(previous["closed"].wait(), timeout=3.0)
            except asyncio.TimeoutError:
                # The previous inference/read may still be unwinding. Claiming
                # here avoids a permanently stuck session; model prediction is
                # still serialized by _PREDICT_LOCK.
                pass
        _CAMERA_ACTIVE_SESSION = session
    return session


def _release_camera_session(session: dict) -> None:
    global _CAMERA_ACTIVE_SESSION

    if _CAMERA_ACTIVE_SESSION is session:
        _CAMERA_ACTIVE_SESSION = None
    session["closed"].set()


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
    import torch

    cuda_available = torch.cuda.is_available()
    # 默认优先使用 GPU；如果请求了 gpu/cuda 但 CUDA 不可用则明确报错。
    requested_mode = str(payload.get("mode", "cuda" if cuda_available else "cpu")).lower()
    mode = "cuda" if requested_mode in ("cuda", "gpu") else "cpu"
    if mode == "cuda" and not cuda_available:
        raise ValueError("当前 PyTorch 环境未启用 CUDA，实时检测仅支持 cpu 模式")
    conf = float(payload.get("conf", settings.CAMERA_CONFIDENCE))
    iou = float(payload.get("iou", settings.CAMERA_IOU))
    if not 0.05 <= conf <= 0.95 or not 0.05 <= iou <= 0.95:
        raise ValueError("conf 和 iou 必须在 0.05 到 0.95 之间")
    conf = max(conf, settings.CAMERA_CONFIDENCE)
    scene_id = payload.get("scene_id")
    if scene_id is not None:
        scene_id = int(scene_id)
        if scene_id < 1:
            raise ValueError("scene_id 必须为正整数")
    camera_url = str(payload.get("camera_url") or "").strip()
    if camera_url:
        camera_url = normalize_ip_webcam_url(camera_url)
    else:
        camera_url = None
    return {
        "mode": mode,
        "conf": conf,
        "iou": iou,
        "scene_id": scene_id,
        "camera_url": camera_url,
    }


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
    capture = None
    frame_reader = None
    session = None
    stopped = None
    control_task = None
    await websocket.accept()
    try:
        initial = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if initial.get("type") != "config":
            raise ValueError("连接后必须先发送 config 消息")
        options = _camera_options(initial)
        stream_url = options["camera_url"] or configured_ip_webcam_url()
        session = await _claim_camera_session()
        stopped = session["stopped"]

        capture = await run_in_threadpool(_open_camera_capture, stream_url)
        frame_reader = _LatestCameraFrame(capture)
        frame_reader.start()
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
                "mode": options["mode"],
                "device": "cuda" if torch.cuda.is_available() else "cpu",
                "target_fps": settings.CAMERA_TARGET_FPS,
                "image_size": settings.CAMERA_IMAGE_SIZE,
                "model": model_context["model_name"],
                "scene": model_context["scene"],
                "source": "IP Webcam",
                "low_latency": True,
                "output_max_width": settings.CAMERA_OUTPUT_MAX_WIDTH,
                "session_id": session["id"],
                "temporal_stabilization": True,
                "stability_min_hits": settings.CAMERA_STABILITY_MIN_HITS,
            }
        )
        control_task = asyncio.create_task(_camera_control(websocket, stopped))
        frame_count = 0
        stabilizer = RealtimeDetectionStabilizer(
            min_hits=settings.CAMERA_STABILITY_MIN_HITS,
            max_misses=settings.CAMERA_STABILITY_MAX_MISSES,
            iou_threshold=settings.CAMERA_STABILITY_IOU,
        )
        previous_result_at = time.perf_counter()
        frame_interval = 1 / max(0.5, settings.CAMERA_TARGET_FPS)
        last_sequence = 0
        last_frame_at = time.perf_counter()
        dropped_frames = 0

        while not stopped.is_set():
            cycle_started = time.perf_counter()
            latest = await run_in_threadpool(frame_reader.latest, last_sequence, 1.0)
            if latest is None:
                if time.perf_counter() - last_frame_at > settings.CAMERA_STALE_TIMEOUT_SECONDS:
                    raise DetectionServiceError("IP Webcam 画面读取超时，请检查手机网络")
                continue
            sequence, frame, captured_at = latest
            dropped_frames += max(0, sequence - last_sequence - 1)
            last_sequence = sequence
            last_frame_at = time.perf_counter()
            raw_result = await run_in_threadpool(
                detection_service.detect_realtime_frame,
                model_context["model"],
                frame,
                conf=options["conf"],
                iou=options["iou"],
                image_size=settings.CAMERA_IMAGE_SIZE,
                jpeg_quality=settings.CAMERA_JPEG_QUALITY,
                output_max_width=settings.CAMERA_OUTPUT_MAX_WIDTH,
                finalize=False,
            )
            stable_detections = stabilizer.update(raw_result["detections"])
            result = await run_in_threadpool(
                detection_service.finalize_realtime_frame,
                frame,
                stable_detections,
                inference_time_ms=raw_result["inference_time_ms"],
                jpeg_quality=settings.CAMERA_JPEG_QUALITY,
                output_max_width=settings.CAMERA_OUTPUT_MAX_WIDTH,
            )
            frame_count += 1
            now = time.perf_counter()
            result.update(
                {
                    "type": "result",
                    "frame_count": frame_count,
                    "fps": round(1 / max(now - previous_result_at, 0.001), 1),
                    "pipeline_latency_ms": round((now - captured_at) * 1000, 1),
                    "dropped_frames": dropped_frames,
                    "source_frame_sequence": sequence,
                    "raw_object_count": len(raw_result["detections"]),
                    "temporal_stabilized": True,
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
        if stopped is not None:
            stopped.set()
        try:
            if control_task:
                control_task.cancel()
                try:
                    await control_task
                except asyncio.CancelledError:
                    pass
            if frame_reader is not None:
                await run_in_threadpool(frame_reader.stop)
            elif capture is not None:
                await run_in_threadpool(capture.release)
        finally:
            if session is not None:
                _release_camera_session(session)
        try:
            if session is not None and session["replaced"]:
                await websocket.close(
                    code=CAMERA_REPLACED_CLOSE_CODE,
                    reason="摄像头检测已由新的页面会话接管",
                )
            else:
                await websocket.close()
        except RuntimeError:
            pass
