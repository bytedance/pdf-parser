"""Logging setup for the ``hi-pdf-parser`` CLI.

* stderr handler with ``[LEVEL] timestamp message`` format; messages are written
  in ``key=value`` style by callers (consistent with the existing
  ``_log_stage_debug`` preference). No structlog.
* ``attach_file_handler`` / ``detach_file_handler`` let the runner mirror stderr
  output into each document's ``logs/stderr.log`` for the duration of its
  processing, via a ``try/finally`` block.
* stdout is reserved exclusively for the JSON envelope and is never touched by
  logging.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_STDERR_FORMAT = "[%(levelname)s] %(asctime)s %(message)s"

# The logger namespace the CLI logs under. File handlers attach to this logger.
CLI_LOGGER_NAME = "hi_pdf_parser.cli"

_stderr_handler: logging.Handler | None = None


def configure_logging(level: int = logging.INFO, quiet: bool = False) -> None:
    """Configure the root ``hi-pdf-parser`` logger to emit to stderr.

    ``quiet`` raises the threshold to WARNING so progress (INFO) logs are muted
    while warnings/errors still surface.
    """
    global _stderr_handler

    logger = logging.getLogger(CLI_LOGGER_NAME)
    logger.propagate = False
    effective_level = logging.WARNING if quiet else level
    logger.setLevel(effective_level)

    if _stderr_handler is None:
        import sys

        _stderr_handler = logging.StreamHandler(stream=sys.stderr)
        _stderr_handler.setFormatter(logging.Formatter(_STDERR_FORMAT))
        logger.addHandler(_stderr_handler)

    _stderr_handler.setLevel(effective_level)


def get_logger() -> logging.Logger:
    return logging.getLogger(CLI_LOGGER_NAME)


def attach_file_handler(path: Path) -> logging.Handler:
    """Attach a FileHandler writing to ``path`` and return it.

    The parent directory must already exist. The returned handler should be
    passed to :func:`detach_file_handler` in a ``finally`` block.
    """
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_STDERR_FORMAT))
    logger = logging.getLogger(CLI_LOGGER_NAME)
    handler.setLevel(logger.level)
    logger.addHandler(handler)
    return handler


def detach_file_handler(handler: logging.Handler) -> None:
    """Detach and close a previously attached file handler."""
    logger = logging.getLogger(CLI_LOGGER_NAME)
    logger.removeHandler(handler)
    handler.close()
