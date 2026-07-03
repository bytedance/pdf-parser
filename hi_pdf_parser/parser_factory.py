"""Shared construction helpers for the PyMuPDF parser."""

from __future__ import annotations

from typing import Any

from .config import PyMuPDFParserConfig
from .parser import PyMuPDFParser


def build_parser_config(
    *,
    extract_images: bool | None = None,
    extract_tables: bool | None = None,
    max_pages: int | None = None,
    skip_header_footer: bool | None = None,
) -> PyMuPDFParserConfig:
    """Build parser config from package defaults plus explicit overrides."""
    values: dict[str, Any] = PyMuPDFParserConfig().model_dump()
    overrides = {
        "extract_images": extract_images,
        "extract_tables": extract_tables,
        "max_pages": max_pages,
        "skip_header_footer": skip_header_footer,
    }
    values.update({key: value for key, value in overrides.items() if value is not None})
    return PyMuPDFParserConfig(**values)


def create_parser(config: PyMuPDFParserConfig | None = None) -> PyMuPDFParser:
    """Create a parser using shared package defaults unless config is supplied."""
    return PyMuPDFParser(config or build_parser_config())
