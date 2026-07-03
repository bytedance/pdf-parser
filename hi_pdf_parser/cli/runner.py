"""单文档编排：``hi-pdf-parser parse`` 的 local-only runner。

职责（对齐 hi-pdf-parser 的输出契约）：

* 校验输入存在性；
* 准备规范化输出目录，挂载 per-document ``logs/stderr.log``；
* 调用 ``hi_pdf_parser.parser.PyMuPDFParser.parse`` 复用项目内解析逻辑；
* 将 blocks 适配为 document.md / manifest.json / profiling.json；
* 返回 ``(envelope, exit_code)``，从不调用 ``sys.exit`` 或打印，便于 batch 聚合。
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..logging_setup import (
    attach_file_handler,
    detach_file_handler,
)
from . import envelope as env, output_writer as ow
from .errors import (
    EXIT_OK,
    CliError,
    InputCorruptError,
    InputFormatUnsupportedError,
    InputNotFoundError,
    PageRangeOutOfBoundsError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from hi_pdf_parser.datamodel import Block

_log = logging.getLogger(__name__)


@dataclass
class ParseConfig:
    out: Path
    page_range: tuple[int, int] | None


def run_parse(input_path: Path, config: ParseConfig) -> tuple[dict[str, Any], int]:
    """处理单个文件；返回 (envelope, exit_code)。"""
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
    stem_dir = ow.prepare_output_dir(config.out, stem)
    handler = attach_file_handler(ow.stderr_log_path(stem_dir))
    try:
        return _run_local(input_path, stem_dir, config)
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


def _run_local(
    input_path: Path, stem_dir: Path, config: ParseConfig
) -> tuple[dict[str, Any], int]:
    _log.info(
        "local_parse_start input=%s page_range=%s",
        input_path,
        config.page_range,
    )
    started_at = time.monotonic()
    blocks, metadata = _parse_with_project_parser(input_path, config.page_range)
    markdown, assets, warnings = _blocks_to_markdown(blocks, stem_dir)
    ow.write_document(stem_dir, markdown)
    duration_ms = int((time.monotonic() - started_at) * 1000)
    page_count = _parsed_page_count(metadata, config.page_range)
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


def _parse_with_project_parser(
    input_path: Path, page_range: tuple[int, int] | None
) -> tuple[list[Block], dict[str, Any]]:
    import fitz  # type: ignore[import-untyped]

    from hi_pdf_parser.config import PyMuPDFParserConfig
    from hi_pdf_parser.parser import PyMuPDFParser

    parser = PyMuPDFParser(
        PyMuPDFParserConfig(
            extract_images=True,
            extract_tables=True,
            skip_header_footer=True,
        )
    )
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
        # parser._open_and_authenticate_document 会把 PyMuPDF 的打开失败包成裸
        # Exception(... from e)，真实类型在 __cause__ 上。EmptyFileError(0 字节)
        # 与 FileDataError(损坏/非 PDF 内容)均为 FileDataError 家族。
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


def _blocks_to_markdown(
    blocks: list[Block], stem_dir: Path
) -> tuple[str, list[dict[str, Any]], list[str]]:
    from PIL import Image

    from hi_pdf_parser.datamodel import ContentType

    md_parts: list[str] = []
    assets: list[dict[str, Any]] = []
    warnings: list[str] = []
    image_counts: dict[int, int] = defaultdict(int)
    any_text = False

    for block in blocks:
        if block.type == ContentType.image:
            page_num = block.areas[0].page_num if block.areas else 0
            image_counts[page_num] += 1
            filename = f"page-{page_num:03d}-figure-{image_counts[page_num]:03d}.png"
            rel_ref = f"images/{filename}"
            target = ow.images_dir(stem_dir) / filename
            image_bytes = base64.b64decode(block.content)
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.save(target, format="PNG")
            assets.append(
                {
                    "asset_id": f"figure_{page_num:03d}_{image_counts[page_num]:03d}",
                    "path": rel_ref,
                    "page": page_num,
                    "bbox": block.areas[0].rect if block.areas else None,
                    "mime": "image/png",
                    "sha256": _sha256_of(target),
                }
            )
            md_parts.append(f"![Figure {image_counts[page_num]}]({rel_ref})")
            continue

        content = block.content.strip()
        if not content:
            continue
        if block.type == ContentType.text:
            any_text = True
        md_parts.append(content)

    if not any_text:
        warnings.append("local_mode_empty_text")

    markdown = "\n\n".join(md_parts).strip()
    return (markdown + "\n") if markdown else "", assets, warnings


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _parsed_page_count(
    metadata: dict[str, Any], page_range: tuple[int, int] | None
) -> int:
    total = int(metadata.get("page_count") or 0)
    if page_range is None or total <= 0:
        return total
    start, end = page_range
    if start > total:
        return 0
    return min(total, end) - max(1, start) + 1


def run_batch(
    inputs: list[Path],
    config: ParseConfig,
    *,
    abort_on_error: bool,
    emit,
) -> int:
    """顺序处理多个文件，返回聚合退出码。

    ``emit`` 在每个 envelope 产生时立即回调（用于按输入顺序流式输出 NDJSON）。

    聚合规则：

    * 全部成功 -> 0
    * 全部失败 -> 首个失败的退出码
    * 部分失败 -> 1
    * ``abort_on_error`` -> 立即停止，返回触发的退出码
    """
    first_failure_code: int | None = None
    failure_codes: list[int] = []
    failures: list[str] = []
    total = len(inputs)

    for input_path in inputs:
        envelope, code = run_parse(input_path, config)
        emit(envelope)
        if code != EXIT_OK:
            if first_failure_code is None:
                first_failure_code = code
            failure_codes.append(code)
            failures.append(str(input_path))
            if abort_on_error:
                _log.error("batch_abort input=%s exit_code=%s", input_path, code)
                return code

    success_count = total - len(failure_codes)
    if not failure_codes:
        return EXIT_OK

    _log.error(
        "batch_failures count=%d/%d files=%s",
        len(failure_codes),
        total,
        ",".join(failures),
    )

    if success_count == 0:
        return first_failure_code or 1
    return 1
