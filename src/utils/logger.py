"""Loguru-based logging configuration for the application."""

import sys
from pathlib import Path

from loguru import logger

from src.core.config import get_settings


def setup_logger() -> None:
    """Configure the loguru logger based on application settings.

    Uses a console sink for source runs and a rotating file sink for all runs.
    """
    settings = get_settings()

    # Remove default loguru handler
    logger.remove()

    if sys.stderr is not None and not getattr(sys, "frozen", False):
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
            colorize=True,
            backtrace=True,
            diagnose=settings.app_debug,
        )

    # File handler – rotated, retained
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path),
        level=settings.log_level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        backtrace=True,
        diagnose=settings.app_debug,
    )

    logger.info("Logger initialised (level={})", settings.log_level)


# Exported logger instance – importable throughout the application
__all__ = ["logger", "setup_logger"]
