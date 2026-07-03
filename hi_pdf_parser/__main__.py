# Copyright (C) 2025 ByteDance Inc
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Unified ``hi-pdf-parser`` command line entry point."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import click
import typer
import uvicorn

from . import artifact_writer as ow, command_envelope as env
from .errors import (
    EXIT_INTERNAL_ERROR,
    EXIT_OK,
    EXIT_USAGE,
    CliError,
    InputCorruptError,
    InputFormatUnsupportedError,
    InputNotFoundError,
    PageRangeOutOfBoundsError,
)
from .logging_setup import attach_file_handler, configure_logging, detach_file_handler
from .page_range import PageSpecError, parse_page_spec
from .parse_runtime import ParseRuntimeOptions
from .settings import UvicornSettings

if TYPE_CHECKING:
    from .datamodel import Block

_log = logging.getLogger(__name__)

app = typer.Typer(
    name="hi-pdf-parser",
    help="PDF Parser CLI and server.",
    epilog="""示例:
  hi-pdf-parser parse report.pdf --out ./out
  hi-pdf-parser batch a.pdf b.pdf --out ./out
  hi-pdf-parser batch --from-file files.txt --out ./out
  hi-pdf-parser -v parse report.pdf --out ./out
  hi-pdf-parser serve --host 0.0.0.0 --port 8000

查看子命令参数:
  hi-pdf-parser parse --help
  hi-pdf-parser batch --help
  hi-pdf-parser serve --help

注意:
  - 全局参数必须放在子命令之前, 例如 `hi-pdf-parser -v parse ...`。
  - parse/batch 仅支持 PDF; 其他格式请使用 docparser。""",
    no_args_is_help=False,
    add_completion=False,
)


@app.callback()
def _configure(
    quiet: Annotated[
        bool,
        typer.Option("--quiet", show_envvar=False, help="关闭包级进度日志。"),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option(
            "-v",
            "--verbose",
            count=True,
            show_envvar=False,
            help="提升包级 stderr 日志级别, 可叠加。",
        ),
    ] = 0,
) -> None:
    level = logging.DEBUG if verbose >= 2 else logging.INFO
    configure_logging(level=level, quiet=quiet)


def _validate_output_format(value: str) -> str:
    if value != "markdown":
        raise typer.BadParameter("--format 当前仅支持 markdown。")
    return value


def _validate_out_naming(value: str) -> str:
    if value != "stem":
        raise typer.BadParameter("--out-naming 当前仅支持 stem。")
    return value


def _validate_pages(pages: str | None) -> str | None:
    if pages is None:
        return None
    try:
        parse_page_spec(pages)
    except PageSpecError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return pages


OutOption = Annotated[
    Path,
    typer.Option("--out", show_envvar=False, help="输出根目录, 默认 ./out。"),
]
OutputFormatOption = Annotated[
    str,
    typer.Option(
        "--format",
        callback=_validate_output_format,
        show_envvar=False,
        help="输出格式, 当前仅支持 markdown。",
    ),
]
PagesOption = Annotated[
    str | None,
    typer.Option(
        "--pages",
        "-p",
        callback=_validate_pages,
        show_envvar=False,
        help="页码范围: 单页 n、区间 a-b、连续页 3,4; 不支持多段非连续范围。",
    ),
]
OutNamingOption = Annotated[
    str,
    typer.Option(
        "--out-naming",
        callback=_validate_out_naming,
        show_envvar=False,
        help="输出命名策略, 当前仅支持 stem。",
    ),
]
FromFileOption = Annotated[
    Path | None,
    typer.Option(
        "--from-file",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        show_envvar=False,
        help="每行一个文件路径的清单文件, 与位置参数二选一。",
    ),
]


def _page_range(pages: str | None) -> tuple[int, int] | None:
    if pages is None:
        return None
    return parse_page_spec(pages)[0]


def _collect_batch_inputs(
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


def _emit_envelope(envelope: dict) -> None:
    typer.echo(env.dumps(envelope))


def _parse_file(
    input_path: Path, out: Path, options: ParseRuntimeOptions
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
            options.page_range,
        )
        started_at = time.monotonic()
        blocks, metadata = _parse_pdf_blocks(input_path, options)
        markdown, assets, warnings = _blocks_to_markdown(blocks, stem_dir)
        ow.write_document(stem_dir, markdown)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        page_count = _parsed_page_count(metadata, options.page_range)
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
    input_path: Path, options: ParseRuntimeOptions
) -> tuple[list[Block], dict[str, Any]]:
    import fitz  # type: ignore[import-untyped]

    from hi_pdf_parser.parser_factory import create_parser

    parser = create_parser()
    try:
        with contextlib.redirect_stdout(sys.stderr):
            return parser.parse(str(input_path), **options.to_kwargs())
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


@app.command(help="解析单个 PDF, stdout 输出单行 JSON envelope。")
def parse(
    file: Annotated[
        Path,
        typer.Argument(help="待解析的单个 PDF 路径。"),
    ],
    out: OutOption = Path("./out"),
    output_format: OutputFormatOption = "markdown",
    pages: PagesOption = None,
    out_naming: OutNamingOption = "stem",
) -> int:
    options = ParseRuntimeOptions(page_range=_page_range(pages))
    envelope, exit_code = _parse_file(file, out, options)
    _emit_envelope(envelope)
    return exit_code


@app.command(help="批量解析多个 PDF, stdout 输出 NDJSON。")
def batch(
    files: Annotated[
        list[Path] | None,
        typer.Argument(help="待解析的多个 PDF 路径。"),
    ] = None,
    from_file: FromFileOption = None,
    abort_on_error: Annotated[
        bool,
        typer.Option(
            "--abort-on-error", show_envvar=False, help="遇到首个失败即停止。"
        ),
    ] = False,
    out: OutOption = Path("./out"),
    output_format: OutputFormatOption = "markdown",
    pages: PagesOption = None,
    out_naming: OutNamingOption = "stem",
) -> int:
    inputs = _collect_batch_inputs(files, from_file)
    options = ParseRuntimeOptions(page_range=_page_range(pages))

    def emit(envelope: dict) -> None:
        _emit_envelope(envelope)

    first_failure_code: int | None = None
    failure_codes: list[int] = []
    failures: list[str] = []
    total = len(inputs)

    for input_path in inputs:
        envelope, code = _parse_file(input_path, out, options)
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


@app.command()
def serve(
    host: Annotated[str | None, typer.Option("--host", help="Server host")] = None,
    port: Annotated[int | None, typer.Option("--port", help="Server port")] = None,
    reload: Annotated[
        bool | None, typer.Option("--reload/--no-reload", help="Enable auto-reload")
    ] = None,
    workers: Annotated[
        int | None, typer.Option("--workers", help="Number of worker processes")
    ] = None,
    root_path: Annotated[
        str | None, typer.Option("--root-path", help="Root path for the app")
    ] = None,
    proxy_headers: Annotated[
        bool | None,
        typer.Option("--proxy-headers/--no-proxy-headers", help="Use proxy headers"),
    ] = None,
    timeout_keep_alive: Annotated[
        int | None,
        typer.Option("--timeout-keep-alive", help="Keep-alive timeout seconds"),
    ] = None,
) -> None:
    from .app import create_app

    settings = UvicornSettings()
    uvicorn.run(
        app=create_app,
        factory=True,
        host=host or settings.host,
        port=port or settings.port,
        reload=reload if reload is not None else settings.reload,
        workers=workers or settings.workers,
        root_path=root_path or settings.root_path,
        proxy_headers=proxy_headers
        if proxy_headers is not None
        else settings.proxy_headers,
        timeout_keep_alive=timeout_keep_alive or settings.timeout_keep_alive,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = app(args=argv, prog_name="hi-pdf-parser", standalone_mode=False)
    except click.exceptions.Exit as exc:
        return exc.exit_code
    except click.Abort:
        click.echo("Aborted!", err=True)
        return EXIT_INTERNAL_ERROR
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code or EXIT_USAGE
    if isinstance(result, int):
        return result
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
