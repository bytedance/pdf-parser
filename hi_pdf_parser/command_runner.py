"""Command execution helpers for local file parsing."""

from __future__ import annotations

import contextlib
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from . import artifact_writer as ow, command_envelope as env
from .errors import (
    EXIT_OK,
    CliError,
    InputCorruptError,
    InputFormatUnsupportedError,
    InputNotFoundError,
    PageRangeOutOfBoundsError,
)
from .logging_setup import attach_file_handler, detach_file_handler

if TYPE_CHECKING:
    from .datamodel import Block

PageRange = tuple[int, int]

_log = logging.getLogger(__name__)


def collect_batch_inputs(
    files: list[Path] | None, from_file: Path | None
) -> list[Path]:
    if from_file and files:
        raise click.UsageError("--from-file 与位置参数 files 不能同时提供。")

    if from_file:
        lines = from_file.read_text(encoding="utf-8").splitlines()
        inputs = [Path(line.strip()) for line in lines if line.strip()]
    else:
        inputs = files or []

    if not inputs:
        raise click.UsageError("batch 需要提供至少一个文件, 或使用 --from-file。")

    seen: dict[str, Path] = {}
    for path in inputs:
        if path.stem in seen:
            raise click.UsageError(
                f"stem 冲突: {path} 与 {seen[path.stem]} 共享输出目录名 '{path.stem}'。"
            )
        seen[path.stem] = path

    return inputs


def parse_file(
    input_path: Path, out: Path, page_range: PageRange | None
) -> tuple[dict[str, Any], int]:
    if not input_path.exists() or not input_path.is_file():
        exc: CliError = InputNotFoundError(f"输入文件不存在: {input_path}")
        return env.error_envelope_from_exc(str(input_path), exc), exc.exit_code

    if input_path.suffix.lower() != ".pdf":
        exc = InputFormatUnsupportedError(
            f"hi-pdf-parser 仅支持 PDF，收到: {input_path.suffix or '(no ext)'}",
            hint="hi-pdf-parser 是离线 PDF 文本提取工具；其他格式请使用 docparser。",
        )
        return env.error_envelope_from_exc(str(input_path), exc), exc.exit_code

    stem = input_path.stem
    stem_dir = ow.prepare_output_dir(out, stem)
    handler = attach_file_handler(ow.stderr_log_path(stem_dir))
    try:
        _log.info(
            "local_parse_start input=%s page_range=%s",
            input_path,
            page_range,
        )
        started_at = time.monotonic()
        blocks, metadata = _parse_pdf_blocks(input_path, page_range)
        markdown, assets, warnings = ow.blocks_to_markdown(blocks, stem_dir)
        ow.write_document(stem_dir, markdown)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        page_count = _parsed_page_count(metadata, page_range)
        _log.info(
            "local_parse_done input=%s pages=%d images=%d duration_ms=%d",
            input_path,
            page_count,
            len(assets),
            duration_ms,
        )

        manifest = ow.build_manifest(
            input_path=str(input_path),
            mode="local",
            mode_used="local",
            status="success",
            assets=assets,
            stats={"pages": page_count, "duration_ms": duration_ms},
            warnings=warnings,
            fallback_reason=None,
        )
        ow.write_manifest(stem_dir, manifest)
        ow.write_profiling(
            stem_dir,
            {"pages": [], "total_duration_ms": duration_ms},
        )

        envelope = env.success_envelope(
            input_path=str(input_path),
            out_dir=str(stem_dir),
            mode="local",
            mode_used="local",
            manifest=manifest,
            fallback_reason=None,
        )
        return envelope, EXIT_OK
    except CliError as exc:
        _log.error(
            "parse_failed input=%s error_type=%s msg=%s",
            input_path,
            exc.error_type,
            exc.message,
        )
        return env.error_envelope_from_exc(str(input_path), exc), exc.exit_code
    except Exception as e:
        _log.exception("parse_internal_error input=%s", input_path)
        envelope = env.error_envelope(
            input_path=str(input_path),
            error_type="INTERNAL_ERROR",
            message=str(e),
            exit_code=1,
        )
        return envelope, 1
    finally:
        detach_file_handler(handler)


def _parse_pdf_blocks(
    input_path: Path, page_range: PageRange | None
) -> tuple[list[Block], dict[str, Any]]:
    import fitz  # type: ignore[import-untyped]

    from hi_pdf_parser.parser import create_parser

    parser = create_parser()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            return parser.parse(str(input_path), page_range=page_range)
    except PermissionError as exc:
        raise InputCorruptError(
            f"PDF 已加密: {input_path}",
            hint="hi-pdf-parser 不支持加密 PDF，请先用 qpdf/pdftk 等工具去除密码后重试。",
        ) from exc
    except ValueError as exc:
        if str(exc).startswith("--pages"):
            total = _extract_total_pages_from_error(str(exc))
            raise PageRangeOutOfBoundsError(
                str(exc),
                hint=f"该 PDF 共 {total} 页，请使用 1-{total} 范围内的页码。"
                if total is not None
                else None,
            ) from exc
        raise
    except Exception as exc:
        if isinstance(exc.__cause__, fitz.FileDataError):
            raise InputCorruptError(
                f"PDF 损坏或为空，无法打开: {input_path}",
                hint="文件可能是 0 字节、被截断或不是有效的 PDF；请确认文件完整后重试。",
            ) from exc
        raise


def _extract_total_pages_from_error(message: str) -> int | None:
    try:
        return int(message.rsplit(" ", 1)[-1])
    except ValueError:
        return None


def _parsed_page_count(metadata: dict[str, Any], page_range: PageRange | None) -> int:
    total = int(metadata.get("page_count") or 0)
    if page_range is None or total <= 0:
        return total
    start, end = page_range
    if start > total:
        return 0
    return min(total, end) - max(1, start) + 1
