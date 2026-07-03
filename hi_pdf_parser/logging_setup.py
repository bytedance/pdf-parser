"""Logging setup for the ``hi-pdf-parser`` package.

Entrypoints decide where package logs go. Library modules keep normal
``logging.getLogger(__name__)`` loggers and do not configure handlers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_STDERR_FORMAT = "[%(levelname)s] %(asctime)s %(message)s"

PACKAGE_LOGGER_NAME = "hi_pdf_parser"

_stderr_handler: logging.Handler | None = None


def configure_logging(level: int = logging.INFO, quiet: bool = False) -> None:
    """Configure package logs for CLI-style stderr output."""
    global _stderr_handler

    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    logger.propagate = False
    effective_level = logging.WARNING if quiet else level
    logger.setLevel(effective_level)

    if _stderr_handler is None:
        import sys

        _stderr_handler = logging.StreamHandler(stream=sys.stderr)
        _stderr_handler.setFormatter(logging.Formatter(_STDERR_FORMAT))
        logger.addHandler(_stderr_handler)

    _stderr_handler.setLevel(effective_level)


def attach_file_handler(path: Path) -> logging.Handler:
    """Attach a FileHandler writing package logs to ``path`` and return it."""
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_STDERR_FORMAT))
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    handler.setLevel(logger.level)
    logger.addHandler(handler)
    return handler


def detach_file_handler(handler: logging.Handler) -> None:
    """Detach and close a previously attached file handler."""
    logger = logging.getLogger(PACKAGE_LOGGER_NAME)
    logger.removeHandler(handler)
    handler.close()
