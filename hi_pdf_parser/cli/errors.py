"""Custom exception family for the hi-pdf-parser CLI and exit-code mapping.

Each CLI failure mode raises a :class:`CliError` subclass carrying a stable
``error_type`` string and an ``exit_code``. The top-level ``main`` catches
:class:`CliError` to build an error envelope and exit with the mapped code.

Exit-code contract:

* ``2``  - CLI usage errors (handled by Typer/Click, not here)
* ``10`` - input problems (not found / unsupported / corrupt PDF)
* ``40`` - output write failure
* ``1``  - any other uncaught error
"""

from __future__ import annotations

# Exit code constants.
EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_USAGE = 2
EXIT_INPUT_ERROR = 10
EXIT_OUTPUT_WRITE_FAILURE = 40


class CliError(Exception):
    """Base class for all CLI errors with a stable error_type and exit_code."""

    error_type: str = "INTERNAL_ERROR"
    exit_code: int = EXIT_INTERNAL_ERROR

    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


class InputNotFoundError(CliError):
    error_type = "INPUT_NOT_FOUND"
    exit_code = EXIT_INPUT_ERROR


class InputFormatUnsupportedError(CliError):
    error_type = "INPUT_FORMAT_UNSUPPORTED"
    exit_code = EXIT_INPUT_ERROR


class PageRangeOutOfBoundsError(CliError):
    error_type = "PAGE_RANGE_OUT_OF_BOUNDS"
    exit_code = EXIT_INPUT_ERROR


class InputCorruptError(CliError):
    """File is encrypted, empty, or otherwise unreadable as the declared format."""

    error_type = "INPUT_CORRUPT"
    exit_code = EXIT_INPUT_ERROR


class OutputWriteError(CliError):
    error_type = "OUTPUT_WRITE_FAILURE"
    exit_code = EXIT_OUTPUT_WRITE_FAILURE
