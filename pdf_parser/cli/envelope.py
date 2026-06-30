"""Stdout envelope construction for the docparser CLI.

``parse`` prints a single-line JSON envelope; ``batch`` prints one envelope per
line (NDJSON). Both success and error results use the same envelope shape so
consumers can branch on the ``status`` field.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .errors import CliError


def success_envelope(
    input_path: str,
    out_dir: str,
    mode: str,
    mode_used: str,
    manifest: dict[str, Any],
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Build a success envelope for a single document."""
    return {
        "status": "success",
        "input": input_path,
        "out": out_dir,
        "mode": mode,
        "mode_used": mode_used,
        "fallback_reason": fallback_reason,
        "outputs": manifest.get("outputs", {}),
        "stats": manifest.get("stats", {}),
        "warnings": manifest.get("warnings", []),
    }


def error_envelope(
    input_path: str,
    error_type: str,
    message: str,
    exit_code: int,
    hint: str | None = None,
) -> dict[str, Any]:
    """Build an error envelope for a single document."""
    return {
        "status": "error",
        "input": input_path,
        "error_type": error_type,
        "message": message,
        "exit_code": exit_code,
        "hint": hint,
    }


def error_envelope_from_exc(input_path: str, exc: CliError) -> dict[str, Any]:
    return error_envelope(
        input_path=input_path,
        error_type=exc.error_type,
        message=exc.message,
        exit_code=exc.exit_code,
        hint=exc.hint,
    )


def dumps(envelope: dict[str, Any]) -> str:
    """Serialize an envelope to a single compact JSON line."""
    return json.dumps(envelope, ensure_ascii=False)
