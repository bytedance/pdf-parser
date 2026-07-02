"""Custom exception family for the docparser CLI and exit-code mapping.

Each CLI failure mode raises a :class:`CliError` subclass carrying a stable
``error_type`` string and an ``exit_code``. The top-level ``main`` catches
:class:`CliError` to build an error envelope and exit with the mapped code.

Exit-code contract (see plan section 9):

* ``2``  - CLI usage errors (handled by Typer/Click, not here)
* ``10`` - input problems (not found / unsupported / missing dependency)
* ``20`` - model service unreachable / errored
* ``21`` - model service timeout
* ``30`` - parse failure (docling reported FAILURE / SKIPPED)
* ``40`` - output write failure
* ``1``  - any other uncaught error
"""

from __future__ import annotations

# Exit code constants.
EXIT_OK = 0
EXIT_INTERNAL_ERROR = 1
EXIT_USAGE = 2
EXIT_INPUT_ERROR = 10
EXIT_MODEL_SERVICE_ERROR = 20
EXIT_MODEL_SERVICE_TIMEOUT = 21
EXIT_PARSE_FAILURE = 30
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


class MissingDependencyError(CliError):
    error_type = "MISSING_DEPENDENCY_PYMUPDF"
    exit_code = EXIT_INPUT_ERROR


class ModelServiceUnreachableError(CliError):
    error_type = "MODEL_SERVICE_UNREACHABLE"
    exit_code = EXIT_MODEL_SERVICE_ERROR


class ModelServiceError(CliError):
    error_type = "MODEL_SERVICE_ERROR"
    exit_code = EXIT_MODEL_SERVICE_ERROR


class ModelServiceTimeoutError(CliError):
    error_type = "MODEL_SERVICE_TIMEOUT"
    exit_code = EXIT_MODEL_SERVICE_TIMEOUT


class ParseFailureError(CliError):
    error_type = "PARSE_FAILURE"
    exit_code = EXIT_PARSE_FAILURE


class OutputWriteError(CliError):
    error_type = "OUTPUT_WRITE_FAILURE"
    exit_code = EXIT_OUTPUT_WRITE_FAILURE


# error_types that represent connection-level remote failures eligible for
# fallback to local mode (see plan section 10).
FALLBACKABLE_ERROR_TYPES = frozenset(
    {
        "MODEL_SERVICE_UNREACHABLE",
        "MODEL_SERVICE_ERROR",
        "MODEL_SERVICE_TIMEOUT",
    }
)
