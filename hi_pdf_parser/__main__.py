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

import logging
import sys
from pathlib import Path
from typing import Annotated, NoReturn, cast

import click
import typer

from .command_envelope import dumps
from .command_runner import PageRange, collect_batch_inputs, parse_file
from .errors import EXIT_INTERNAL_ERROR, EXIT_OK, EXIT_USAGE
from .logging_setup import configure_logging
from .settings import UvicornSettings

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


def _parse_pages(pages: str | None) -> PageRange | None:
    if pages is None:
        return None

    raw = pages.strip()
    hint = (
        "MVP 仅支持单页（如 5）、连续区间（如 1-20）或连续逗号（如 3,4）；"
        "不支持非连续页码（如 1,5,9）、反序或 0/负数。"
    )

    def fail() -> NoReturn:
        raise typer.BadParameter(f"无效的 --pages 取值: {pages!r}。{hint}")

    if not raw or ("-" in raw and "," in raw):
        fail()

    if "-" in raw:
        parts = raw.split("-")
        if len(parts) != 2:
            fail()
        start, end = _to_positive_int(parts[0], fail), _to_positive_int(parts[1], fail)
        if start > end:
            fail()
        return (start, end)

    if "," in raw:
        parts = raw.split(",")
        if len(parts) != 2:
            fail()
        start, end = _to_positive_int(parts[0], fail), _to_positive_int(parts[1], fail)
        if end != start + 1:
            fail()
        return (start, end)

    page = _to_positive_int(raw, fail)
    return (page, page)


def _to_positive_int(token: str, on_error) -> int:
    token = token.strip()
    if not token.isdigit():
        on_error()
    value = int(token)
    if value < 1:
        on_error()
    return value


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
        callback=_parse_pages,
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
    page_range = cast(PageRange | None, pages)
    envelope, exit_code = parse_file(file, out, page_range)
    typer.echo(dumps(envelope))
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
    inputs = collect_batch_inputs(files, from_file)
    page_range = cast(PageRange | None, pages)

    first_failure_code: int | None = None
    failure_codes: list[int] = []
    failures: list[str] = []
    total = len(inputs)

    for input_path in inputs:
        envelope, code = parse_file(input_path, out, page_range)
        typer.echo(dumps(envelope))
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
    try:
        import uvicorn

        from .app import create_app
    except ImportError as e:
        typer.echo(
            "Server dependencies are not installed. "
            "Install them with `pip install 'hi-pdf-parser[server]'`.",
            err=True,
        )
        raise typer.Exit(1) from e

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
