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

from .envelope import dumps
from .errors import EXIT_INTERNAL_ERROR, EXIT_OK, EXIT_USAGE
from .logging_setup import configure_logging
from .runner import PageRange, collect_input_paths, parse_file
from .settings import UvicornSettings

_log = logging.getLogger(__name__)

app = typer.Typer(
    name="hi-pdf-parser",
    help="PDF Parser CLI and server.",
    epilog="""Examples:
  hi-pdf-parser parse report.pdf --out ./out
  hi-pdf-parser parse a.pdf b.pdf --out ./out
  hi-pdf-parser -v parse report.pdf --out ./out
  hi-pdf-parser serve --host 0.0.0.0 --port 8000

Show subcommand help:
  hi-pdf-parser parse --help
  hi-pdf-parser serve --help

Notes:
  - Global options must appear before the subcommand, e.g. `hi-pdf-parser -v parse ...`.
  - parse accepts PDF files only; use docparser for other formats.""",
    no_args_is_help=False,
    add_completion=False,
)


@app.callback()
def _configure(
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", show_envvar=False, help="Disable package progress logs."
        ),
    ] = False,
    verbose: Annotated[
        int,
        typer.Option(
            "-v",
            "--verbose",
            count=True,
            show_envvar=False,
            help="Increase the package stderr log level; repeat for debug logs.",
        ),
    ] = 0,
) -> None:
    level = logging.DEBUG if verbose >= 2 else logging.INFO
    configure_logging(level=level, quiet=quiet)


def _validate_output_format(value: str) -> str:
    if value != "markdown":
        raise typer.BadParameter("--format currently supports markdown only.")
    return value


def _validate_out_naming(value: str) -> str:
    if value != "stem":
        raise typer.BadParameter("--out-naming currently supports stem only.")
    return value


def _parse_pages(pages: str | None) -> PageRange | None:
    if pages is None:
        return None

    raw = pages.strip()
    hint = (
        "MVP supports a single page (for example 5), an inclusive range "
        "(for example 1-20), or two consecutive comma-separated pages "
        "(for example 3,4); non-contiguous pages (for example 1,5,9), "
        "reversed ranges, and 0 or negative values are not supported."
    )

    def fail() -> NoReturn:
        raise typer.BadParameter(f"Invalid --pages value: {pages!r}. {hint}")

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
    typer.Option(
        "--out", show_envvar=False, help="Output root directory; default is ./out."
    ),
]
OutputFormatOption = Annotated[
    str,
    typer.Option(
        "--format",
        callback=_validate_output_format,
        show_envvar=False,
        help="Output format; currently only markdown is supported.",
    ),
]
PagesOption = Annotated[
    str | None,
    typer.Option(
        "--pages",
        "-p",
        callback=_parse_pages,
        show_envvar=False,
        help="Page range: single page n, range a-b, or consecutive pages 3,4; non-contiguous ranges are not supported.",
    ),
]
OutNamingOption = Annotated[
    str,
    typer.Option(
        "--out-naming",
        callback=_validate_out_naming,
        show_envvar=False,
        help="Output naming strategy; currently only stem is supported.",
    ),
]


@app.command(help="Parse one or more PDFs and print JSON envelopes to stdout.")
def parse(
    files: Annotated[
        list[Path] | None,
        typer.Argument(help="PDF file(s) to parse."),
    ] = None,
    out: OutOption = Path("./out"),
    output_format: OutputFormatOption = "markdown",
    pages: PagesOption = None,
    out_naming: OutNamingOption = "stem",
) -> int:
    inputs = collect_input_paths(files)
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

    success_count = total - len(failure_codes)
    if not failure_codes:
        return EXIT_OK

    _log.error(
        "parse_failures count=%d/%d files=%s",
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
