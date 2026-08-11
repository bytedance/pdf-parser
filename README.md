# PDF Parser

A HTTP server converting PDF file to text blocks.

This project uses [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/) and complies with its open-source licensing obligations.

## Installation

To use PDF Parser, simply install `hi-pdf-parser` from your package manager, e.g. pip:

```bash
pip install hi-pdf-parser
```

Install the optional server dependencies when running the HTTP server:

```bash
pip install 'hi-pdf-parser[server]'
```

## CLI

The official command is `hi-pdf-parser`.

```bash
hi-pdf-parser parse report.pdf --out ./out
hi-pdf-parser parse a.pdf b.pdf --out ./out
hi-pdf-parser serve --host 0.0.0.0 --port 8000
```

`parse` writes Markdown, assets, manifest, and logs under `<out>/<stem>/`, and emits one JSON envelope per input on stdout. `serve` starts the HTTP API server and requires the `server` extra.

## Developing

### Prepare

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --all-groups --extra server
```

### Coding Style Guidelines

To run the checks on-demand repeatedly until it passes. If you see mypy errors you might need to provide typing hints where requested.

```bash
uv run pre-commit run --all-files
```
