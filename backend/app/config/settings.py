from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用全局配置"""

    # ── 应用基础配置 ──────────────────────────────────
    APP_NAME: str = "Vision Pay"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # ── 数据库配置 ────────────────────────────────────
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "vp_agent"
    DB_USER: str = "vp_admin"
    DB_PASSWORD: str = "vp_admin"

    @property
    def DATABASE_URL(self) -> str:
        """构造 PostgreSQL 连接字符串"""
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # ── 日志配置 ────────────────────────────────────
    LOG_DIR: str = "../.runtime/backend-logs"  # 日志目录(相对于 backend/)
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 单文件最大 10MB
    LOG_BACKUP_COUNT: int = 5  # 保留 5 份历史日志
    SQL_ECHO: bool = False  # 仅在需要调试 SQL 时打开

    # ── 训练配置 ──────────────────────────────────────
    TRAIN_OUTPUT_DIR: str = "runs/train"
    DATASET_BASE_DIR: str = "datasets"
    YOLO_CONFIG_DIR: str = ".ultralytics"

    # ── 检测推理配置 ──────────────────────────────────
    DETECTION_OUTPUT_DIR: str = "runs/detect"
    DETECTION_UPLOAD_DIR: str = ".runtime/uploads"
    DETECTION_MODEL_PATH: str = ""
    DETECTION_MAX_FILE_MB: int = 20
    DETECTION_MAX_BATCH_SIZE: int = 30
    DETECTION_VIDEO_MAX_FILE_MB: int = 50
    VIDEO_FRAME_SAMPLE_RATE: int = 5
    VIDEO_MAX_KEY_FRAMES: int = 50
    VIDEO_TASK_TTL_SECONDS: int = 3600
    VIDEO_RESULT_DIR: str = "runs/detect/video-results"

    # ── IP Webcam 实时检测配置 ─────────────────────────
    # 前端可以覆盖该默认地址；后端仍会校验为安全的局域网 HTTP 地址。
    IP_WEBCAM_URL: str = "http://10.172.52.70:8080"
    CAMERA_CONFIDENCE: float = 0.25
    CAMERA_IOU: float = 0.45
    CAMERA_IMAGE_SIZE: int = 416
    CAMERA_TARGET_FPS: float = 3.0
    CAMERA_JPEG_QUALITY: int = 70

    # ── DeepSeek Agent 配置（OpenAI 兼容接口）─────────
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    # DeepSeek 控制台显示的 v4 flash 模型标识可在 .env 中覆盖。
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TEMPERATURE: float = 0.1

    # ── Redis 配置 ────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def REDIS_URL(self) -> str:
        """构造 Redis 连接字符串"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # ── MinIO 配置 ────────────────────────────────────
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "vp-images"
    MINIO_SECURE: bool = False

    # ── JWT 认证配置 ──────────────────────────────────
    JWT_SECRET_KEY: str = "your-super-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # ── 模拟支付配置 ──────────────────────────────────
    MOCK_PAYMENT_EXPIRE_MINUTES: int = 10

    # ── CORS 配置 ────────────────────────────────────
    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,"
        "http://127.0.0.1:5173,http://localhost:8080"
    )

    @property
    def cors_origins_list(self) -> list:
        """将 CORS 配置字符串转为列表"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 忽略 .env 中未在 Settings 定义的字段


# 创建全局单例，其他模块直接 import 使用
settings = Settings()
