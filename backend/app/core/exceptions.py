from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from jose import JWTError
from app.core.logger import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI):
    """注册全局异常处理器"""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # 处理 HTTP 业务异常(如400、401、404等)
        # 4xx 错误用 WARNING 级别(客户端问题)
        if 400 <= exc.status_code < 500:
            logger.warning(
                "HTTP %d: %s | path=%s",
                exc.status_code,
                exc.detail,
                request.url.path,
            )
        else:
            logger.error(
                "HTTP %d: %s | path=%s",
                exc.status_code,
                exc.detail,
                request.url.path,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": exc.detail,
                "data": None,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        # 处理 Pydantic 参数验证异常
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            errors.append(f"{field}: {error['msg']}")

        logger.warning(
            "参数验证失败 | path=%s | errors=%s",
            request.url.path,
            errors,
        )
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "message": "参数验证失败",
                "data": errors,
            },
        )

    @app.exception_handler(JWTError)
    async def jwt_exception_handler(request: Request, exc: JWTError):
        """处理 JWT Token 解析异常"""
        logger.warning("JWT 验证失败 | path=%s | error=%s", request.url.path, str(exc))
        return JSONResponse(
            status_code=401,
            content={
                "code": 401,
                "message": "无效的认证凭据",
                "data": None,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        # 处理所有未预期的异常(兜底处理器)
        # 使用 exc_info=True 记录完整堆栈信息
        logger.error(
            "未处理的异常 | path=%s | method=%s | error=%s",
            request.url.path,
            request.method,
            str(exc),
            exc_info=True,  # 关键:记录完整堆栈
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "服务器内部错误",
                "data": None,
            },
        )
