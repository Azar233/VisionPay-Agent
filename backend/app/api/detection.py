"""Shared upload helpers and the checkout IP-camera detection socket."""

from __future__ import annotations

import asyncio
import re
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import torch
from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.concurrency import run_in_threadpool
from app.api.camera import configured_ip_webcam_url, normalize_ip_webcam_url
from app.config.settings import settings
from app.services.detection_service import DetectionServiceError, detection_service
from app.services.track_aggregator import TrackRegistry

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


def _camera_options(payload: dict) -> dict:
    """Validate the initial config message accepted by the camera socket."""
    import torch

    cuda_available = torch.cuda.is_available()
    requested_mode = str(payload.get("mode", "cuda" if cuda_available else "cpu")).lower()
    mode = "cuda" if requested_mode in ("cuda", "gpu") else "cpu"
    warning = None
    # 请求 GPU 但环境不支持时自动降级到 CPU，而不是直接断开连接。
    if mode == "cuda" and not cuda_available:
        warning = "当前 PyTorch 环境未启用 CUDA，实时检测已自动切换为 cpu 模式"
        mode = "cpu"
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
    accumulate = payload.get("accumulate")
    if accumulate is None:
        accumulate = True
    elif not isinstance(accumulate, bool):
        accumulate = str(accumulate).lower() in ("true", "1", "yes", "on")
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
        "accumulate": accumulate,
        "warning": warning,
    }


async def _camera_control(websocket: WebSocket, stopped: asyncio.Event, reset_scan: asyncio.Event) -> None:
    """Listen for an explicit close/reset message or a disconnected browser."""
    try:
        while not stopped.is_set():
            message = await websocket.receive_json()
            if message.get("type") == "close":
                stopped.set()
                return
            if message.get("type") == "reset_scan":
                reset_scan.set()
    except (WebSocketDisconnect, RuntimeError):
        stopped.set()


async def _frame_sender(
    websocket: WebSocket,
    send_queue: asyncio.Queue,
    stopped: asyncio.Event,
    frame_interval: float,
) -> None:
    """Finalize (annotate/price) and send frames, overlapped with the next inference.

    The inference loop stays strictly serial (ByteTrack state); this coroutine is
    the only WebSocket writer once started. The bounded queue applies backpressure,
    so no inferred frame — and none of its confirmed events — is dropped here.
    """
    frame_count = 0
    previous_result_at = time.perf_counter()
    while True:
        item = await send_queue.get()
        if item is None:
            return
        cycle_started = time.perf_counter()
        try:
            result = await run_in_threadpool(
                detection_service.finalize_realtime_frame,
                item["frame"],
                item["detections"],
                inference_time_ms=item["inference_time_ms"],
                jpeg_quality=settings.CAMERA_JPEG_QUALITY,
                output_max_width=settings.CAMERA_OUTPUT_MAX_WIDTH,
                price_detections=item["price_detections"],
            )
        except DetectionServiceError as exc:
            message = str(exc)
        except Exception as exc:
            message = f"实时检测异常: {exc}"
        else:
            message = None
        if message is not None:
            stopped.set()
            try:
                await websocket.send_json({"type": "error", "message": message})
            except RuntimeError:
                pass
            return
        frame_count += 1
        now = time.perf_counter()
        result.update(
            {
                "type": "result",
                "frame_count": frame_count,
                "fps": round(1 / max(now - previous_result_at, 0.001), 1),
                "pipeline_latency_ms": round((now - item["captured_at"]) * 1000, 1),
                "dropped_frames": item["dropped_frames"],
                "source_frame_sequence": item["sequence"],
                "raw_object_count": item["raw_object_count"],
                "temporal_stabilized": True,
                "scan_total_objects": item["scan_total_objects"],
                "scan_class_counts": item["scan_class_counts"],
                "new_confirmed": item["new_confirmed"],
            }
        )
        previous_result_at = now
        try:
            await websocket.send_json(result)
        except (WebSocketDisconnect, RuntimeError):
            stopped.set()
            return
        # 输出帧率上限仍由 CAMERA_TARGET_FPS 控制，但不再串行阻塞推理循环。
        remaining = frame_interval - (time.perf_counter() - cycle_started)
        if remaining > 0:
            try:
                await asyncio.wait_for(stopped.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass
        if stopped.is_set():
            return


async def _stop_sender(
    send_queue: asyncio.Queue | None,
    sender_task: asyncio.Task | None,
) -> None:
    """Drain the frame sender via a sentinel, cancelling only as a last resort."""
    if send_queue is None or sender_task is None or sender_task.done():
        return
    try:
        send_queue.put_nowait(None)
    except asyncio.QueueFull:
        try:
            send_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        try:
            send_queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
    try:
        await asyncio.wait_for(sender_task, timeout=2.0)
    except asyncio.TimeoutError:
        sender_task.cancel()
        try:
            await sender_task
        except asyncio.CancelledError:
            pass
    except asyncio.CancelledError:
        raise
    except Exception:
        # sender 自身已处理业务异常；这里兜底，避免清理动作掩盖主流程异常
        pass


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
    send_queue = None
    sender_task = None
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
                "warning": options.get("warning"),
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
                "accumulate": options["accumulate"],
            }
        )
        reset_scan = asyncio.Event()
        control_task = asyncio.create_task(_camera_control(websocket, stopped, reset_scan))
        newly_confirmed: list[dict[str, Any]] = []

        def _new_registry() -> TrackRegistry:
            return TrackRegistry(
                min_hits=settings.CAMERA_STABILITY_MIN_HITS,
                max_misses=settings.CAMERA_STABILITY_MAX_MISSES,
                min_confidence=options["conf"],
                on_track_confirmed=lambda record: newly_confirmed.append(
                    {
                        "track_id": record.track_id,
                        "class_id": record.class_id,
                        "class_name": record.class_name,
                        "confidence": round(record.best_confidence, 4),
                    }
                ),
            )

        registry = _new_registry()
        frame_interval = 1 / max(0.5, settings.CAMERA_TARGET_FPS)
        last_sequence = 0
        last_frame_at = time.perf_counter()
        dropped_frames = 0
        send_queue = asyncio.Queue(maxsize=1)
        sender_task = asyncio.create_task(
            _frame_sender(websocket, send_queue, stopped, frame_interval)
        )

        frame_count = 0
        last_snapshot: dict[str, Any] | None = None
        inference_stride = max(1, settings.CAMERA_INFERENCE_STRIDE)

        while not stopped.is_set():
            latest = await run_in_threadpool(frame_reader.latest, last_sequence, 1.0)
            if latest is None:
                if time.perf_counter() - last_frame_at > settings.CAMERA_STALE_TIMEOUT_SECONDS:
                    raise DetectionServiceError("IP Webcam 画面读取超时，请检查手机网络")
                continue
            sequence, frame, captured_at = latest
            dropped_frames += max(0, sequence - last_sequence - 1)
            last_sequence = sequence
            last_frame_at = time.perf_counter()
            frame_count += 1

            if reset_scan.is_set():
                registry = _new_registry()
                newly_confirmed.clear()
                last_snapshot = None
                reset_scan.clear()
                # 排空队列中滞留的重置前快照，保证重扫后下一帧即是新累计状态
                while True:
                    try:
                        send_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            # 跳帧推理：每隔 inference_stride 帧做一次真正的推理，
            # 中间帧复用最近一次推理结果，降低 GPU/CPU 压力。
            should_infer = last_snapshot is None or (frame_count % inference_stride) == 0

            if should_infer:
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
                    tracking=True,
                )
                registry.update(sequence, time.perf_counter(), raw_result["detections"])
                stable_detections = registry.active_tracks()
                accumulate = options["accumulate"]
                price_detections = None
                if accumulate:
                    price_detections = [
                        {"class_id": record.class_id, "class_name": record.class_name}
                        for record in registry.confirmed_tracks()
                    ]
                confirmed_batch = list(newly_confirmed)
                newly_confirmed.clear()
                last_snapshot = {
                    "detections": stable_detections,
                    "price_detections": price_detections,
                    "raw_object_count": len(raw_result["detections"]),
                    "scan_total_objects": registry.total_unique,
                    "scan_class_counts": registry.dedup_class_counts(),
                    "inference_time_ms": raw_result["inference_time_ms"],
                }
            else:
                # 非推理帧复用上一次快照，不重复触发累计确认事件。
                confirmed_batch = []

            if last_snapshot is None:
                continue

            item = {
                "frame": frame,
                "detections": last_snapshot["detections"],
                "price_detections": last_snapshot["price_detections"],
                "inference_time_ms": last_snapshot["inference_time_ms"],
                "captured_at": captured_at,
                "sequence": sequence,
                "dropped_frames": dropped_frames,
                "raw_object_count": last_snapshot["raw_object_count"],
                "scan_total_objects": last_snapshot["scan_total_objects"],
                "scan_class_counts": last_snapshot["scan_class_counts"],
                "new_confirmed": confirmed_batch,
            }
            # 背压：队列满说明 sender 还在处理上一帧，等它取走后再继续；
            # 已准备的帧（含确认事件、计价快照）在这里不会被丢弃。
            enqueued = False
            while not stopped.is_set():
                if reset_scan.is_set() or sender_task.done():
                    break
                try:
                    send_queue.put_nowait(item)
                    enqueued = True
                    break
                except asyncio.QueueFull:
                    await asyncio.sleep(0.005)
            if not enqueued:
                # 重置/停止/sender 退出：丢弃当前快照，交给下一轮统一处理
                continue
    except asyncio.TimeoutError:
        await _stop_sender(send_queue, sender_task)
        await websocket.send_json({"type": "error", "message": "等待摄像头配置超时"})
    except WebSocketDisconnect:
        pass
    except (ValueError, DetectionServiceError) as exc:
        await _stop_sender(send_queue, sender_task)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except RuntimeError:
            pass
    except Exception as exc:
        await _stop_sender(send_queue, sender_task)
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
            await _stop_sender(send_queue, sender_task)
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
