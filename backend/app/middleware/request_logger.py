import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.logger import get_logger

logger = get_logger("request")

# 不记录日志的路径前缀(高频或无意义请求)
SKIP_PATHS = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/api/health",  # 健康检查频率高,不记录
]


class RequestLogMiddleware(BaseHTTPMiddleware):
    """API 请求日志中间件"""

    async def dispatch(self, request: Request, call_next):
        # 1. 检查是否需要跳过日志记录
        path = request.url.path
        if any(path.startswith(skip) for skip in SKIP_PATHS):
            return await call_next(request)

        # 2. 记录请求开始
        method = request.method
        client_ip = request.client.host if request.client else "unknown"
        # 获取请求体大小(如果有)
        content_length = request.headers.get("content-length", "0")

        logger.info(
            "%s %s | ip=%s | size=%s",
            method,
            path,
            client_ip,
            content_length,
        )

        # 3. 记录开始时间
        start_time = time.time()

        # 4. 调用下一个处理器(执行实际的业务逻辑)
        response = await call_next(request)

        # 5. 计算耗时
        duration_ms = (time.time() - start_time) * 1000

        # 6. 记录请求结束状态
        status_code = response.status_code

        # 根据状态码选择不同的日志级别
        if status_code >= 500:
            logger.error(
                "%s %s | status=%d | %.1fms",
                method,
                path,
                status_code,
                duration_ms,
            )
        elif status_code >= 400:
            logger.warning(
                "%s %s | status=%d | %.1fms",
                method,
                path,
                status_code,
                duration_ms,
            )
        else:
            logger.info(
                "%s %s | status=%d | %.1fms",
                method,
                path,
                status_code,
                duration_ms,
            )

        return response
