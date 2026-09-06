from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import logs_dir

LOG_FILE_NAME = "app.log"


def setup_logging() -> logging.Logger:
    log_dir = logs_dir()
    log_file = log_dir / LOG_FILE_NAME

    root = logging.getLogger()
    if not any(getattr(handler, "baseFilename", None) == str(log_file) for handler in root.handlers):
        root.setLevel(logging.INFO)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(handler)

    # Telethon can be noisy at INFO. Keep its transport details available only when
    # they are warnings/errors, and never enable wire-level DEBUG logging here.
    logging.getLogger("telethon").setLevel(logging.WARNING)

    logger = logging.getLogger("telegram_exporter")
    logger.info("Application logging initialized: %s", log_file)
    return logger


def log_file_path():
    return logs_dir() / LOG_FILE_NAME
