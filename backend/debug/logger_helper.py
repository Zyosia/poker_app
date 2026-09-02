# logger_helper.py
"""
Simple logger helper for Python applications.

Features:
- Console logging
- Optional file logging
- Multiple log levels
- Easy to reuse across projects

Usage:
    from logger_helper import get_logger

    logger = get_logger("my_app")

    logger.info("Application started")
    logger.warning("Something looks suspicious")
    logger.error("Something failed")
"""

import logging
import sys
from pathlib import Path

# Prevent duplicate configuration
_LOGGERS = {}


def get_logger(
    name: str = "default",
    log_folder: str = "default_folder",
    log_filename: str | None = "default",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    Create and return a configured logger.

    Args:
        name: Logger name
        log_file: Optional log file path
        level: Logging level

    Returns:
        Configured logger instance
    """

    # Reuse existing logger
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Log format
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    # File handler (optional)
    if log_filename:
        log_path = Path(f"../logs/{log_folder}/{log_filename}.log")

        # Create logs directory if needed
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    _LOGGERS[name] = logger
    return logger


from datetime import datetime
from zoneinfo import ZoneInfo


def create_log_folder(log_folder_name):
    # Current timestamp (clean, sortable format)
    timestamp = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d_%H-%M")
    # Final folder name
    folder_name = f"{log_folder_name}_{timestamp}_log"
    # Build path (adjust base directory if needed)
    log_path = Path("../logs") / folder_name
    # Create the directory
    log_path.mkdir(parents=True, exist_ok=True)
    return folder_name


# Quick Test
if __name__ == "__main__":
    logger = get_logger("test")

    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
