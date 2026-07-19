"""Proxy an IP Webcam MJPEG stream for the checkout frontend."""

import ipaddress
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config.settings import settings


router = APIRouter(prefix="/api/camera", tags=["手机摄像头"])
ALLOWED_STREAM_PATHS = {"/video", "/videofeed"}


def normalize_ip_webcam_url(raw_url: str) -> str:
    """Validate a LAN or loopback IP Webcam URL and return its direct MJPEG endpoint."""
    try:
        parsed = urlsplit(raw_url.strip())
        hostname = parsed.hostname or ""
        if hostname.lower() == "localhost":
            hostname = "127.0.0.1"
        address = ipaddress.ip_address(hostname)
        port = parsed.port
    except (ValueError, TypeError) as exc:
        raise ValueError("请输入有效的局域网 IP Webcam 地址") from exc

    if parsed.scheme != "http":
        raise ValueError("IP Webcam 地址必须以 http:// 开头")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("暂不支持包含账号、参数或片段的摄像头地址")
    if not (address.is_private or address.is_loopback) or address.is_link_local:
        raise ValueError("只允许连接局域网地址或本机地址")
    if port is None:
        port = 8080

    path = parsed.path.rstrip("/")
    if not path:
        path = "/video"
    if path not in ALLOWED_STREAM_PATHS:
        raise ValueError("地址路径仅支持 /video 或 /videofeed")

    host = f"[{address}]" if address.version == 6 else str(address)
    return urlunsplit(("http", f"{host}:{port}", path, "", ""))


def configured_ip_webcam_url() -> str:
    """Return the validated server-side IP Webcam MJPEG endpoint."""
    if not settings.IP_WEBCAM_URL.strip():
        raise ValueError("后端尚未配置 IP_WEBCAM_URL")
    return normalize_ip_webcam_url(settings.IP_WEBCAM_URL)


@router.get("/ip-webcam/config", summary="获取 IP Webcam 公共状态")
async def ip_webcam_config():
    """Expose readiness without leaking the private LAN camera address."""
    try:
        stream_url = configured_ip_webcam_url()
    except ValueError as exc:
        return {"configured": False, "message": str(exc)}
    parsed = urlsplit(stream_url)
    return {
        "configured": True,
        "source": "IP Webcam",
        "endpoint": parsed.path,
    }


@router.get("/ip-webcam/stream")
async def ip_webcam_stream(url: str | None = Query(None, max_length=200)):
    """Relay MJPEG bytes so HTTPS/mixed-content and CORS do not affect the UI."""
    try:
        stream_url = normalize_ip_webcam_url(url) if url else configured_ip_webcam_url()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client = httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0),
        trust_env=False,
    )
    try:
        request = client.build_request("GET", stream_url)
        response = await client.send(request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail="无法连接 IP Webcam，请检查地址和手机网络") from exc

    content_type = response.headers.get("content-type", "").lower()
    if response.status_code != 200:
        await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"IP Webcam 返回状态码 {response.status_code}")
    if "multipart/x-mixed-replace" not in content_type and "image/jpeg" not in content_type:
        await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail="该地址没有返回 MJPEG 视频流")

    async def relay_bytes():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        relay_bytes(),
        media_type=response.headers.get("content-type"),
        headers={"Cache-Control": "no-store"},
    )
