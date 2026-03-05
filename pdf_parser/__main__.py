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

import json
import logging
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Optional

import typer
import uvicorn

from .app import create_app
from .config import PyMuPDFParserConfig
from .datamodel import Block
from .parser import PyMuPDFParser
from .settings import UvicornSettings

app = typer.Typer(name="pdf-parser", help="PDF Parser CLI and server")


def _validate_pdf_file(file_path: str) -> Path:
    p = Path(file_path)
    if not p.exists():
        raise typer.BadParameter(f"File does not exist: {file_path}")
    if not p.is_file():
        raise typer.BadParameter(f"Path is not a file: {file_path}")
    return p


class OutputFormat(StrEnum):
    json = "json"
    text = "text"


def _output_results(
    blocks: list[Block],
    metadata: dict[str, Any],
    output_file: Optional[str],
    output_format: OutputFormat,
) -> None:
    def _text_lines() -> Iterator[str]:
        prev_page = -1
        for b in blocks:
            page_num: int | None = None
            if b.areas:
                page_num = b.areas[0].page_num
            if page_num is not None and page_num != prev_page:
                yield f"-------------- Page {page_num} --------------"
                prev_page = page_num
            yield b.content

    if output_format == OutputFormat.text:
        if output_file:
            Path(output_file).write_text("\n".join(_text_lines()), encoding="utf-8")
            typer.echo(f"Results written to: {output_file}")
        else:
            for line in _text_lines():
                typer.echo(line)
        return

    result = {"blocks": [b.model_dump() for b in blocks], "metadata": metadata}
    if output_file:
        Path(output_file).write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
        typer.echo(f"Results written to: {output_file}")
    else:
        typer.echo(json.dumps(result, ensure_ascii=False))


@app.command()
def parse(
    pdf_file: Annotated[str, typer.Argument(help="Path to the PDF file to parse")],
    output: Annotated[
        Optional[str],
        typer.Option("-o", "--output", help="Output file path (default: stdout)"),
    ] = None,
    extract_images: Annotated[
        bool,
        typer.Option(
            "--extract-images/--no-extract-images", help="Extract images from the PDF"
        ),
    ] = True,
    extract_tables: Annotated[
        bool,
        typer.Option(
            "--extract-tables/--no-extract-tables", help="Extract tables from the PDF"
        ),
    ] = True,
    skip_header_footer: Annotated[
        bool,
        typer.Option(
            "--skip-header-footer/--no-skip-header-footer",
            help="Skip header and footer detection",
        ),
    ] = True,
    max_pages: Annotated[
        Optional[int],
        typer.Option(
            "--max-pages",
            help="Maximum number of pages to process (default: all pages)",
        ),
    ] = None,
    password: Annotated[
        Optional[str],
        typer.Option("--password", help="Password for encrypted PDF files"),
    ] = None,
    format: Annotated[
        OutputFormat, typer.Option("--format", help="Output format")
    ] = OutputFormat.text,
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Enable verbose logging")
    ] = False,
) -> None:
    if verbose:
        logging.basicConfig(level=logging.INFO)
    pdf_path = _validate_pdf_file(pdf_file)
    cfg: dict[str, Any] = {
        "extract_images": extract_images,
        "extract_tables": extract_tables,
        "skip_header_footer": skip_header_footer,
    }
    if max_pages is not None:
        cfg["max_pages"] = max_pages
    config = PyMuPDFParserConfig(**cfg)
    parser = PyMuPDFParser(config)
    try:
        typer.echo(f"Parsing PDF: {pdf_file}", err=True)
        blocks, metadata = parser.parse(
            str(pdf_path),
            extract_images=extract_images,
            extract_tables=extract_tables,
            password=password,
        )
        typer.echo(f"Extracted {len(blocks)} blocks", err=True)
        _output_results(blocks, metadata, output, format)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except PermissionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error parsing PDF: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def serve(
    host: Annotated[Optional[str], typer.Option("--host", help="Server host")] = None,
    port: Annotated[Optional[int], typer.Option("--port", help="Server port")] = None,
    reload: Annotated[
        Optional[bool], typer.Option("--reload/--no-reload", help="Enable auto-reload")
    ] = None,
    workers: Annotated[
        Optional[int], typer.Option("--workers", help="Number of worker processes")
    ] = None,
    root_path: Annotated[
        Optional[str], typer.Option("--root-path", help="Root path for the app")
    ] = None,
    proxy_headers: Annotated[
        Optional[bool],
        typer.Option("--proxy-headers/--no-proxy-headers", help="Use proxy headers"),
    ] = None,
    timeout_keep_alive: Annotated[
        Optional[int],
        typer.Option("--timeout-keep-alive", help="Keep-alive timeout seconds"),
    ] = None,
) -> None:
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


if __name__ == "__main__":
    app()
