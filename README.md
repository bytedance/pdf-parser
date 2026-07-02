# PDF Parser

A HTTP server converting PDF file to text blocks.

This project uses [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/) and complies with its open-source licensing obligations.

## CLI

The official command is `hi-pdf-parser`.

```bash
hi-pdf-parser parse report.pdf --out ./out
hi-pdf-parser batch a.pdf b.pdf --out ./out
hi-pdf-parser serve --host 0.0.0.0 --port 8000
```

`parse` and `batch` write Markdown, assets, manifest, and logs under `<out>/<stem>/`, and emit JSON envelopes on stdout. `serve` starts the HTTP API server.

## Developing

### Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), and then install pre-commit:

```bash
uv tool install pre-commit --with pre-commit-uv --force-reinstall
```

### Coding Style Guidelines

To run the checks on-demand repeatedly until it passes. If you see mypy errors you might need to provide typing hints where requested.

```bash
uv run pre-commit run --all-files
```
