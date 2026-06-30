"""``--pages`` specification parsing.

MVP supports a single page (``5``), a single continuous range (``1-20``) or a
continuous comma form (``3,4`` meaning pages 3 through 4). Non-continuous specs
(``1,5,9``), ranges with extra parts (``2-3,7``), reversed ranges, zero and
negative values are rejected with a usage error.

The public return type is ``list[tuple[int, int]]`` to leave room for future
multi-range support; for the MVP the list always has length 1.
"""

from __future__ import annotations

import argparse


def parse_page_spec(spec: str) -> list[tuple[int, int]]:
    """Parse a ``--pages`` spec into a list of (start, end) inclusive ranges.

    Raises ``argparse.ArgumentTypeError`` on any invalid / non-continuous spec
    so argparse reports it as a usage error (exit code 2).
    """
    raw = spec.strip()
    hint = (
        "MVP 仅支持单页（如 5）、连续区间（如 1-20）或连续逗号（如 3,4）；"
        "不支持非连续页码（如 1,5,9）、反序或 0/负数。"
    )

    def _fail() -> list[tuple[int, int]]:
        raise argparse.ArgumentTypeError(f"无效的 --pages 取值: {spec!r}。{hint}")

    if not raw:
        _fail()

    if "-" in raw and "," in raw:
        _fail()

    if "-" in raw:
        parts = raw.split("-")
        if len(parts) != 2:
            _fail()
        start, end = _to_int(parts[0], _fail), _to_int(parts[1], _fail)
        if start < 1 or end < 1 or start > end:
            _fail()
        return [(start, end)]

    if "," in raw:
        parts = raw.split(",")
        if len(parts) != 2:
            _fail()
        start, end = _to_int(parts[0], _fail), _to_int(parts[1], _fail)
        if start < 1 or end < 1:
            _fail()
        # comma form must be continuous: end == start + 1
        if end != start + 1:
            _fail()
        return [(start, end)]

    page = _to_int(raw, _fail)
    if page < 1:
        _fail()
    return [(page, page)]


def _to_int(token: str, on_error) -> int:
    token = token.strip()
    if not token.isdigit():
        on_error()
    return int(token)
