"""
Structured logging configuration for production use.

All modules should use get_logger(__name__) instead of print().
Log level is controlled by LOG_LEVEL env var (default: INFO in production, DEBUG in dev).
"""

import logging
import os
import sys
from pathlib import Path


def configure_logging() -> None:
    """One-time global logging configuration."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on re-initialization
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers[0] = handler

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "urllib3", "sentence_transformers", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a module-level logger with the configured format."""
    return logging.getLogger(name)
