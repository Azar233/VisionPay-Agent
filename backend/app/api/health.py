from fastapi import APIRouter
from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["健康检查"])


@router.get("/api/health")
async def health_check():
    """基础健康检查 (用于 Docker/负载均衡探活)"""
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "status": "healthy",
            # 如果你的 settings 中没有 APP_NAME 和 APP_VERSION，可以直接写死字符串
            "app_name": getattr(settings, "APP_NAME", "My Agent Platform"),
            "version": getattr(settings, "APP_VERSION", "0.1.0"),
        },
    }


@router.get("/api/health/detail")
async def health_check_detail():
    """详细健康检查 (用于监控面板，检查各组件连通性)"""
    services = {}

    # 1. 检查 PostgreSQL
    try:
        from sqlalchemy import text
        from app.database.session import SessionLocal

        db = SessionLocal()
        # 使用 text() 兼容 SQLAlchemy 2.0 语法
        db.execute(text("SELECT 1"))
        db.close()
        services["database"] = {"status": "healthy", "message": "PostgreSQL 连接正常"}
    except Exception as e:
        services["database"] = {
            "status": "unhealthy",
            "message": f"PostgreSQL 连接失败: {str(e)}",
        }
        logger.error("PostgreSQL 健康检查失败: %s", str(e))

    # 2. 检查 Redis
    try:
        import redis

        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        r.close()
        services["redis"] = {"status": "healthy", "message": "Redis 连接正常"}
    except Exception as e:
        services["redis"] = {
            "status": "unhealthy",
            "message": f"Redis 连接失败: {str(e)}",
        }
        logger.error("Redis 健康检查失败: %s", str(e))

    # 3. 检查 MinIO
    try:
        from app.storage.minio_client import MinIOClient

        minio = MinIOClient()
        minio.client.list_buckets()
        services["minio"] = {"status": "healthy", "message": "MinIO 连接正常"}
    except Exception as e:
        services["minio"] = {
            "status": "unhealthy",
            "message": f"MinIO 连接失败: {str(e)}",
        }
        logger.error("MinIO 健康检查失败: %s", str(e))

    # 汇总状态
    all_healthy = all(s["status"] == "healthy" for s in services.values())
    return {
        "code": 200,
        "message": "ok",
        "data": {
            "status": "healthy" if all_healthy else "degraded",
            "app_name": getattr(settings, "APP_NAME", "My Agent Platform"),
            "version": getattr(settings, "APP_VERSION", "0.1.0"),
            "services": services,
        },
    }
