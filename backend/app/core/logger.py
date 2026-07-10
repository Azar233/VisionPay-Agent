import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config.settings import settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_log_dir() -> Path:
    log_dir = Path(settings.LOG_DIR)
    if not log_dir.is_absolute():
        log_dir = BACKEND_ROOT / log_dir
    return log_dir.resolve()


LOG_DIR = _resolve_log_dir()
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 日志格式
LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

initialized = False


def _log_level(level_name: str, default: int = logging.INFO) -> int:
    return getattr(logging, str(level_name).upper(), default)


def _quiet_noisy_loggers() -> None:
    """Keep third-party development watchers and drivers from flooding stdout."""

    for logger_name in [
        "watchfiles",
        "watchfiles.main",
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "sqlalchemy",
        "sqlalchemy.engine",
        "minio",
        "httpx",
        "multipart",
    ]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def setup_logging():
    global initialized
    if initialized:
        return
    initialized = True

    root_logger = logging.getLogger()
    app_level = _log_level(settings.LOG_LEVEL)
    root_logger.setLevel(app_level)

    _quiet_noisy_loggers()

    if any(getattr(handler, "_visionpay_handler", False) for handler in root_logger.handlers):
        return

    # 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(app_level)
    console_handler.setFormatter(formatter)
    console_handler._visionpay_handler = True
    root_logger.addHandler(console_handler)

    # 文件 Handler (轮转)
    file_path = LOG_DIR / "app.log"
    file_handler = RotatingFileHandler(
        filename=file_path,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler._visionpay_handler = True
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
